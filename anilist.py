# coding=utf-8
import logging
import re
from logging.handlers import RotatingFileHandler
from typing import Dict, List, Optional

import inflect
import coloredlogs

from custom_mappings import AnilistCustomMapping
from embyclasses import dataclass
from embyclasses import EmbyWatchedSeries, EmbyWatchedMovie
from graphql import fetch_user_list, search_by_name, search_by_id, update_item

logger = logging.getLogger("EmbyAniSync")
CUSTOM_MAPPINGS: Dict[str, List[AnilistCustomMapping]] = {}
ANILIST_EMBY_EPISODE_COUNT_PRIORITY = False

# Set this to True for logging failed AniList matches to
# failed_matches.txt file
ANILIST_LOG_FAILED_MATCHES = False


def int_to_roman_numeral(decimal: int) -> str:
    if not isinstance(decimal, type(1)):
        return decimal
    if not 0 < decimal < 4000:
        return str(decimal)
    ints = (1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1)
    nums = ("M", "CM", "D", "CD", "C", "XC", "L", "XL", "X", "IX", "V", "IV", "I")
    result = []
    for i, number in enumerate(ints):
        count = int(decimal / number)
        result.append(nums[i] * count)
        decimal -= number * count
    return "".join(result)


def log_to_file(message: str):
    file = open("failed_matches.txt", "a+", encoding="utf-8")
    file.write(f"{message}\n")
    file.close()


def clean_failed_matches_file():
    try:
        # create or overwrite the file with empty content
        open("failed_matches.txt", 'w', encoding="utf-8").close()
    except BaseException:
        pass


@dataclass
class AnilistItem:
    anilist_id: int
    item_type: str
    item_format: str
    source: str
    status: str
    media_status: str
    progress: int
    season: str
    episodes: int
    title_english: str
    title_romaji: str
    synonyms: List[str]
    started_year: int
    ended_year: int
    isMovie: bool


def process_user_list(username: str, token: str) -> Optional[List[AnilistItem]]:
    logger.info(f"[ANILIST] Retrieving AniList list for user: {username}")
    anilist_items = []
    try:
        list_items = fetch_user_list(username, token)
        if not list_items:
            logger.critical(f"[ANILIST] Failed to return list for user: {username}")
            return None
        else:
            for item in list_items:
                for media_collection in item.MediaListCollection.lists:
                    if hasattr(media_collection, "entries"):
                        for list_entry in media_collection.entries:
                            if (hasattr(list_entry, "status")
                                    and list_entry.status in ["CURRENT", "PLANNING", "COMPLETED", "DROPPED", "PAUSED", "REPEATING"]
                                    and list_entry.media is not None):
                                item_obj = mediaitem_to_object(list_entry)
                                anilist_items.append(item_obj)
    except BaseException as exception:
        logger.critical(f"[ANILIST] Failed to return list for user: {username}", exception)
        return None

    logger.info(f"[ANILIST] Found {len(anilist_items)} anime series on list")
    return anilist_items


def search_item_to_obj(item) -> Optional[AnilistItem]:
    try:
        if item:
            return mediaitem_to_object(item.data)
    except BaseException:
        pass
    return None


def mediaitem_to_object(media_item) -> AnilistItem:
    anilist_id = media_item.media.id
    item_type = ""
    item_format = ""
    source = ""
    status = ""
    media_status = ""
    progress = 0
    season = ""
    episodes = 0
    title_english = ""
    title_romaji = ""
    synonyms = []
    started_year = 0
    ended_year = 0
    isMovie = False

    if hasattr(media_item, "status"):
        status = media_item.status
    if hasattr(media_item, "progress"):
        progress = media_item.progress
    if hasattr(media_item.media, "status"):
        media_status = media_item.media.status
    if hasattr(media_item.media, "type"):
        item_type = media_item.media.type
    if hasattr(media_item.media, "format"):
        item_format = media_item.media.format
        if item_format == "MOVIE":
            isMovie = True
    if hasattr(media_item.media, "source"):
        source = media_item.media.source
    if hasattr(media_item.media, "season"):
        season = media_item.media.season
    if hasattr(media_item.media, "episodes"):
        episodes = media_item.media.episodes
    if hasattr(media_item.media.title, "english"):
        title_english = media_item.media.title.english
    if hasattr(media_item.media.title, "romaji"):
        title_romaji = media_item.media.title.romaji
    if hasattr(media_item.media, "synonyms"):
        synonyms = media_item.media.synonyms
    if hasattr(media_item.media.startDate, "year"):
        started_year = media_item.media.startDate.year
    if hasattr(media_item.media.endDate, "year"):
        ended_year = media_item.media.endDate.year

    item = AnilistItem(
        anilist_id,
        item_type,
        item_format,
        source,
        status,
        media_status,
        progress,
        season,
        episodes,
        title_english,
        title_romaji,
        synonyms,
        started_year,
        ended_year,
        isMovie
    )
    return item


def match_to_emby(anilist_items: List[AnilistItem], emby_items, token: str):
    if type(emby_items) is not list:
        emby_items = [emby_items]
    logger.info("[ANILIST] Matching Emby items to Anilist")
    for emby_item in emby_items:
        if hasattr(emby_item, "seasons"):
            emby_item: EmbyWatchedSeries
            emby_seasons = emby_item.seasons
        else:
            emby_item: EmbyWatchedMovie
        emby_title = emby_item.title
        emby_title_sort = emby_item.title_sort
        emby_title_original = emby_item.title_original
        emby_year = emby_item.year
        emby_anilist_id = emby_item.anilist_id

        custom_mapping_seasons_anilist_id = 0
        mapped_season_count = 0
        emby_watched_episode_count_custom_mapping = 0

        logger.info("--------------------------------------------------")

        # Might be a better way to check whether item is a movie or show, but this works, however might break function on line 259? Haven't had any issues so far.
        if hasattr(emby_item, "seasons"):
            # Check if we have custom mappings for all seasons (One Piece for example)
            if len(emby_seasons) > 1:
                custom_mapping_season_count = 0
                for emby_season in emby_seasons:
                    season_mappings = retrieve_season_mappings(
                        emby_title, emby_season.season_number
                    )
                    matched_id = 0
                    if season_mappings:
                        matched_id = season_mappings[0].anime_id
                        if custom_mapping_seasons_anilist_id in (0, matched_id):
                            emby_watched_episode_count_custom_mapping += emby_season.episodes_played
                            custom_mapping_season_count += 1

                    custom_mapping_seasons_anilist_id = matched_id

                # If we had custom mappings for multiple seasons with the same ID use
                # cumulative episode count and skip per season processing
                if custom_mapping_season_count > 1:
                    logger.warning(
                        "[ANILIST] Found same custom mapping id for multiple seasons "
                        "so not using per season processing but updating as one | "
                        f"title: {emby_title} | anilist id: {custom_mapping_seasons_anilist_id} | "
                        f"total watched episodes: {emby_watched_episode_count_custom_mapping}"
                    )

                    add_or_update_show_by_id(
                        anilist_items, emby_title, emby_year, True, emby_watched_episode_count_custom_mapping, custom_mapping_seasons_anilist_id, token
                    )
                    mapped_season_count = custom_mapping_season_count

                    if custom_mapping_season_count == len(emby_seasons):
                        return

            # Start processing of any remaining seasons
            for emby_season in emby_seasons[mapped_season_count:]:
                season_number = emby_season.season_number

                emby_watched_episode_count = emby_season.episodes_played
                if emby_watched_episode_count == 0:
                    logger.info(
                        f"[ANILIST] Series {emby_title} has 0 watched episodes for "
                        f"season {season_number}, skipping"
                    )
                    continue
        else:
            # Custom mapping for movies (Using the existing methos for season mappings seems to work fine with just hardcoding season number to 1) (But again, function on line 259??)
            # Using the mappings https://raw.githubusercontent.com/RickDB/PlexAniSync-Custom-Mappings/main/movies-tmdb.en.yaml)
            movie_mapping = retrieve_season_mappings(emby_title, 1)
            matched_id = 0
            if movie_mapping:
                matched_id = movie_mapping[0].anime_id
                logger.warning(
                    f"[ANILIST] Found custom mapping for movie {emby_title}"
                )
                add_or_update_movie_by_id(anilist_items, emby_title, emby_year, True, True, matched_id, token)


        matched_anilist_series = []
        skip_year_check = False

        # for first season use regular search
        if not hasattr(emby_item, 'seasons') or season_number == 1:
            found_match = False
            emby_title_clean = clean_title(emby_title)
            emby_title_sort_clean = clean_title(emby_title_sort)
            emby_title_original_clean = clean_title(emby_title_original)
            emby_title_without_year = re.sub(r"\(\d{4}\)", "", emby_title).strip()
            emby_title_sort_without_year = re.sub(r"\(\d{4}\)", "", emby_title_sort).strip()
            emby_title_original_without_year = re.sub(r"\(\d{4}\)", "", emby_title_original).strip()

            potential_titles = [
                emby_title.lower(),
                emby_title_sort.lower(),
                emby_title_original.lower(),
                emby_title_clean,
                emby_title_sort_clean,
                emby_title_original_clean,
                emby_title_without_year,
                emby_title_sort_without_year,
                emby_title_original_without_year,
            ]

            # Remove duplicates from potential title list
            potential_titles_cleaned = [
                i
                for n, i in enumerate(potential_titles)
                if i not in potential_titles[:n]
            ]
            potential_titles = list(potential_titles_cleaned)

            season_mappings = retrieve_season_mappings(emby_title, 1)
            # Custom mapping check - check user list
            if season_mappings:
                if hasattr(emby_item, 'seasons'):
                    watchcounts = map_watchcount_to_seasons(emby_title, season_mappings, emby_season.episodes_played)

                    for anime_id, watchcount in watchcounts.items():
                        logger.info(
                            f"[ANILIST] Used custom mapping | title: {emby_title} | season: {season_number} | anilist id: {anime_id}"
                        )

                        add_or_update_show_by_id(anilist_items, emby_title, emby_year, True, watchcount, anime_id, token)
                else:
                    logger.info(
                            f"[ANILIST] Used custom mapping | title: {emby_title}"
                        )

                    add_or_update_movie_by_id(anilist_items, emby_title, emby_year, True, True, season_mappings[0].anime_id, token)
                # If custom match found continue to next
                continue

            # Reordered checks from above to ensure that custom mappings always take precedent
            if emby_anilist_id:
                logger.info(f"[ANILIST] Series {emby_title} has Anilist ID {emby_anilist_id} in its metadata, using that for updating")
                if hasattr(emby_item, 'seasons'):
                    add_or_update_show_by_id(anilist_items, emby_title, emby_year, True, emby_watched_episode_count, emby_anilist_id, token)
                else:
                    add_or_update_movie_by_id(anilist_items, emby_title, emby_year, True, True, emby_anilist_id, token)
                continue

            # Regular matching
            if found_match is False:
                for item in anilist_items:
                    match_series_against_potential_titles(item, potential_titles, matched_anilist_series)

            # Series not listed so search for it
            if not all(matched_anilist_series) or not matched_anilist_series:
                logger.warning(f"[ANILIST] Emby item was not on your AniList list: {emby_title}")

                potential_titles_search = [
                    emby_title.lower(),
                    emby_title_sort.lower(),
                    emby_title_original.lower(),
                    emby_title_without_year,
                    emby_title_sort_without_year,
                    emby_title_original_without_year,
                ]

                # Remove duplicates from potential title list
                potential_titles_search_cleaned = [
                    i
                    for n, i in enumerate(potential_titles_search)
                    if i not in potential_titles_search[:n]
                ]
                potential_titles_search = []
                potential_titles_search = list(potential_titles_search_cleaned)

                media_id_search = None
                for potential_title in potential_titles_search:
                    logger.warning(
                        f"[ANILIST] Searching best match using title: {potential_title}"
                    )
                    media_id_search = find_id_best_match(potential_title, emby_year, token)

                    if media_id_search:
                        if hasattr(emby_item, 'seasons'):
                            logger.warning(
                                f"[ANILIST] Adding new series id to list: {media_id_search} | Emby episodes watched: {emby_watched_episode_count}"
                            )
                            add_by_id(
                                media_id_search,
                                emby_title,
                                emby_year,
                                emby_watched_episode_count,
                                False,
                                token
                            )
                            break
                        else:
                            logger.warning(
                                f"[ANILIST] Adding new movie id to list: {media_id_search}"
                            )
                            add_by_id(
                                media_id_search,
                                emby_title,
                                emby_year,
                                1,
                                False,
                                token
                            )
                            break

                if not media_id_search:
                    error_message = (
                        f"[ANILIST] Failed to find valid match on AniList for: {emby_title}"
                    )
                    logger.error(error_message)
                    if ANILIST_LOG_FAILED_MATCHES:
                        log_to_file(error_message)

            # Series exists on list so checking if update required
            else:
                if hasattr(emby_item, 'seasons'):
                    update_entry(
                        emby_title,
                        emby_year,
                        emby_watched_episode_count,
                        matched_anilist_series,
                        skip_year_check,
                        token
                    )
                else:
                    update_entry(
                        emby_title,
                        emby_year,
                        1,
                        matched_anilist_series,
                        skip_year_check,
                        token
                    )
                matched_anilist_series = []
        else:
            media_id_search = None
            # ignore the Emby year since Emby does not have years for seasons
            skip_year_check = True
            season_mappings = retrieve_season_mappings(emby_title, season_number)
            if season_mappings:
                watchcounts = map_watchcount_to_seasons(emby_title, season_mappings, emby_season.episodes_played)

                for anime_id, watchcount in watchcounts.items():
                    logger.info(
                        f"[ANILIST] Used custom mapping |  title: {emby_title} | season: {season_number} | anilist id: {anime_id}"
                    )
                    add_or_update_show_by_id(anilist_items, emby_title, emby_year, True, watchcount, anime_id, token)

                # If custom match found continue to next
                continue
            else:
                if emby_year is not None:
                    media_id_search = find_id_season_best_match(
                        emby_title, season_number, emby_year
                    , token)
                else:
                    logger.error(
                        "[ANILIST] Skipped season lookup as Emby did not supply "
                        "a show year for {emby_title}, recommend checking Emby Web "
                        "and correcting the show year manually."
                    )

            emby_title_lookup = emby_title
            if media_id_search:
                add_or_update_show_by_id(anilist_items, emby_title, emby_year, skip_year_check, emby_watched_episode_count, media_id_search, token)
            else:
                error_message = (
                    f"[ANILIST] Failed to find valid season title match on AniList for: {emby_title_lookup} season {season_number}"
                )
                logger.error(error_message)

                if ANILIST_LOG_FAILED_MATCHES:
                    log_to_file(error_message)


def find_mapped_series(anilist_series: List[AnilistItem], anime_id: int):
    # TODO Int comparison wasn't working for me? $#@!
    return next(filter(lambda s: str(s.anilist_id) == str(anime_id), anilist_series), None)


def match_series_against_potential_titles(
    series: AnilistItem, potential_titles: List[str], matched_anilist_series: List[AnilistItem]
):
    if series.title_english:
        if series.title_english.lower() in potential_titles:
            matched_anilist_series.append(series)
        else:
            series_title_english_clean = clean_title(series.title_english)
            if series_title_english_clean in potential_titles:
                matched_anilist_series.append(series)
    if series.title_romaji:
        if series.title_romaji.lower() in potential_titles:
            if series not in matched_anilist_series:
                matched_anilist_series.append(series)
        else:
            series_title_romaji_clean = clean_title(series.title_romaji)
            if series_title_romaji_clean in potential_titles:
                if series not in matched_anilist_series:
                    matched_anilist_series.append(series)
    if series.synonyms:
        for synonym in series.synonyms:
            if synonym.lower() in potential_titles:
                if series not in matched_anilist_series:
                    matched_anilist_series.append(series)
            else:
                synonym_clean = clean_title(synonym)
                if synonym_clean in potential_titles:
                    matched_anilist_series.append(series)


def find_id_season_best_match(title: str, season: int, year: int, token: str) -> Optional[int]:
    media_id = None
    # logger.warning('[ANILIST] Searching  AniList for title: %s | season: %s' % (title, season))
    match_title = clean_title(title)
    match_year = int(year)

    match_title_season_suffix1 = f"{match_title} {int_to_roman_numeral(season)}"
    match_title_season_suffix2 = f"{match_title} season {season}"
    match_title_season_suffix3 = f"{match_title} part {season}"
    match_title_season_suffix4 = f"{match_title} {season}"

    # oridinal season (1st 2nd etc..)
    try:
        p_engine = inflect.engine()
        match_title_season_suffix5 = f"{match_title} {p_engine.ordinal(season)} season"
    except BaseException:
        logger.error(
            "Error while converting season to ordinal string, make sure Inflect pip package is installed"
        )
        match_title_season_suffix5 = match_title_season_suffix2

    # oridinal season - variation 1 (1st 2nd Thread) - see AniList ID: 21000
    try:
        p_engine = inflect.engine()
        match_title_season_suffix6 = f"{match_title} {p_engine.ordinal(season)} thread"
    except BaseException:
        logger.error(
            "Error while converting season to ordinal string, make sure Inflect pip package is installed"
        )
        match_title_season_suffix6 = match_title_season_suffix2

    potential_titles = [
        match_title_season_suffix1.lower().strip(),
        match_title_season_suffix2.lower().strip(),
        match_title_season_suffix3.lower().strip(),
        match_title_season_suffix4.lower().strip(),
        match_title_season_suffix5.lower().strip(),
        match_title_season_suffix6.lower().strip(),
    ]

    list_items = search_by_name(title, token)
    if list_items:
        for item in list_items:
            if item[0] is not None and item[0].media:
                for media_item in item[0].media:
                    title_english = ""
                    title_english_for_matching = ""
                    title_romaji = ""
                    title_romaji_for_matching = ""
                    started_year = ""

                    if hasattr(media_item.title, "english") and media_item.title.english is not None:
                        title_english = media_item.title.english
                        title_english_for_matching = clean_title(title_english)
                    if hasattr(media_item.title, "romaji") and media_item.title.romaji is not None:
                        title_romaji = media_item.title.romaji
                        title_romaji_for_matching = clean_title(title_romaji)
                    if hasattr(media_item.startDate, "year") and media_item.startDate.year is not None:
                        started_year = int(media_item.startDate.year)
                    else:
                        logger.warning(
                            "[ANILIST] Anilist series did not have year attribute so skipping this result and moving to next: "
                            f"{title_english} | {title_romaji}"
                        )
                        continue

                    for potential_title in potential_titles:
                        potential_title = clean_title(potential_title)
                        # logger.info('Comparing AniList: %s | %s[%s] <===> %s' %
                        #  (title_english_for_matching, title_romaji_for_matching, started_year, potential_title))
                        if title_english_for_matching == potential_title:
                            if started_year < match_year:
                                logger.warning(
                                    f"[ANILIST] Found match: {title_english} [{media_id}] | "
                                    f"skipping as it was released before first season ({started_year} <==> {match_year})"
                                )
                            else:
                                media_id = media_item.id
                                logger.info(
                                    f"[ANILIST] Found match: {title_english} [{media_id}]"
                                )
                                break
                        if title_romaji_for_matching == potential_title:
                            if started_year < match_year:
                                logger.warning(
                                    f"[ANILIST] Found match: {title_romaji} [{media_id}] | "
                                    f"skipping as it was released before first season ({started_year} <==> {match_year})"
                                )
                            else:
                                media_id = media_item.id
                                logger.info(
                                    f"[ANILIST] Found match: {title_romaji} [{media_id}]"
                                )
                                break
    if media_id == 0:
        logger.error(f"[ANILIST] No match found for title: {title}")
    return media_id


def find_id_best_match(title: str, year: int, token: str) -> Optional[int]:
    media_id = None
    # logger.warning('[ANILIST] Searching  AniList for title: %s' % (title))
    match_title = clean_title(title)
    match_year = str(year)

    list_items = search_by_name(title, token)
    if list_items:
        for item in list_items:
            if item[0] is not None and item[0].media:
                for media_item in item[0].media:
                    title_english = ""
                    title_english_for_matching = ""
                    title_romaji = ""
                    title_romaji_for_matching = ""
                    synonyms = ""
                    synonyms_for_matching = ""
                    started_year = ""

                    if hasattr(media_item.title, "english") and media_item.title.english is not None:
                        title_english = media_item.title.english
                        title_english_for_matching = clean_title(title_english)
                    if hasattr(media_item.title, "romaji") and media_item.title.romaji is not None:
                        title_romaji = media_item.title.romaji
                        title_romaji_for_matching = clean_title(title_romaji)
                    if hasattr(media_item.startDate, "year"):
                        started_year = str(media_item.startDate.year)

                    # logger.info('Comparing AniList: %s | %s[%s] <===> %s[%s]' % (title_english, title_romaji, started_year, match_title, match_year))
                    if (
                        match_title == title_english_for_matching
                        and match_year == started_year
                    ):
                        media_id = media_item.id
                        logger.warning(
                            f"[ANILIST] Found match: {title_english} [{media_id}]"
                        )
                        break
                    if (
                        match_title == title_romaji_for_matching
                        and match_year == started_year
                    ):
                        media_id = media_item.id
                        logger.warning(
                            f"[ANILIST] Found match: {title_romaji} [{media_id}]"
                        )
                        break
                    if hasattr(media_item, "synonyms") and media_item.synonyms is not None:
                        for synonym in media_item.synonyms:
                            synonyms = synonym
                            synonyms_for_matching = clean_title(synonyms)
                            if (
                                match_title == synonyms_for_matching
                                and match_year == started_year
                            ):
                                media_id = media_item.id
                                logger.warning(
                                    f"[ANILIST] Found match in synonyms: {synonyms} [{media_id}]"
                                )
                                break
                    if (
                        match_title == title_romaji_for_matching
                        and match_year != started_year
                    ):
                        logger.info(
                            f"[ANILIST] Found match however started year is a mismatch: {title_romaji} [AL: {started_year} <==> Emby: {match_year}] "
                        )
                    elif (
                        match_title == title_english_for_matching
                        and match_year != started_year
                    ):
                        logger.info(
                            f"[ANILIST] Found match however started year is a mismatch: {title_english} [AL: {started_year} <==> Emby: {match_year}] "
                        )
    if media_id is None:
        logger.error(f"[ANILIST] No match found for title: {title}")
    return media_id


def add_or_update_show_by_id(anilist_items: List[AnilistItem], emby_title: str, emby_year: int, skip_year_check: bool, watched_episodes: int, anime_id: int, token: str):
    # print(anilist_series)
    # print(anime_id)
    series = find_mapped_series(anilist_items, anime_id)
    if series:
        logger.info(
            f"[ANILIST] Updating series: {series.title_english} | Episodes watched: {watched_episodes}"
        )
        update_entry(
            emby_title,
            emby_year,
            watched_episodes,
            [series],
            skip_year_check,
            token
        )
    else:
        logger.warning(
            f"[ANILIST] Adding new series id to list: {anime_id} | Episodes watched: {watched_episodes}"
        )
        add_by_id(
            anime_id,
            emby_title,
            emby_year,
            watched_episodes,
            skip_year_check,
            token
        )

def add_or_update_movie_by_id(anilist_items: List[AnilistItem], emby_title: str, emby_year: int, skip_year_check: bool, isWatched: bool, anime_id: int, token: str):
    movie = find_mapped_series(anilist_items, anime_id)
    if movie:
        logger.info(f"[ANILIST] Updating movie: {movie.title_english} | Watched: {isWatched}")
        update_entry(
            emby_title,
            emby_year,
            int(isWatched == True),
            [movie],
            skip_year_check,
            token
        )
    else:
        logger.warning(f"[ANILIST] Adding new movie to list: {anime_id} | Watched: {isWatched}")
        add_by_id(
            anime_id,
            emby_title,
            emby_year,
            int(isWatched == True),
            skip_year_check,
            token
        )


def add_by_id(
    anilist_id: int, emby_title: str, emby_year: int, emby_watched_episode_count: int, ignore_year: bool, token: str
):
    media_lookup_result = search_by_id(anilist_id, token)
    if media_lookup_result:
        anilist_obj = search_item_to_obj(media_lookup_result)
        if anilist_obj:
            update_entry(
                emby_title,
                emby_year,
                emby_watched_episode_count,
                [anilist_obj],
                ignore_year,
                token
            )
        else:
            logger.error(
                "[ANILIST] failed to get anilist object for list adding, skipping item"
            )
    else:
        logger.error(
            f"[ANILIST] failed to get anilist search result for id: {anilist_id}"
        )


def update_entry(
    title: str, year: int, watched_episode_count: int, matched_anilist_item: List[AnilistItem], ignore_year: bool, token: str
):
    for item in matched_anilist_item:
        status = ""
        logger.info(f"[ANILIST] Found AniList entry for Emby title: {title}")
        if hasattr(item, "status"):
            status = item.status
        # print(status)
        if status == "COMPLETED":
            logger.info(
                "[ANILIST] Item is already marked as completed on AniList so skipping update"
            )
            return

        if hasattr(item, "started_year") and year != item.started_year:
            if ignore_year is False:
                logger.error(
                    f"[ANILIST] Item year did not match (skipping update) => Emby has {year} and AniList has {item.started_year}"
                )
                continue
            elif ignore_year is True:
                logger.info(
                    f"[ANILIST] Item year did not match however skip year check was given so adding anyway => "
                    f"Emby has {year} and AniList has {item.started_year}"
                )

        if item.isMovie:
            update_item(item.anilist_id, watched_episode_count, "COMPLETED", token)

        anilist_total_episodes = 0
        anilist_episodes_watched = 0
        anilist_media_status = ""

        if hasattr(item, "media_status"):
            anilist_media_status = item.media_status
        if hasattr(item, "episodes"):
            if item.episodes is not None:
                try:
                    anilist_total_episodes = int(item.episodes)
                except BaseException:
                    logger.error(
                        "Series has unknown total total episodes on AniList "
                        "(not an Integer), will most likely not match up properly"
                    )
                    anilist_total_episodes = 0
            else:
                logger.error(
                    "Series has no total episodes which is normal for shows "
                    "with undetermined end-date otherwise can be invalid info "
                    "on AniList (NoneType), using Emby watched count as fallback"
                )
                anilist_total_episodes = watched_episode_count
        if hasattr(item, "progress"):
            try:
                anilist_episodes_watched = int(item.progress)
            except BaseException:
                pass

        if (
            watched_episode_count >= anilist_total_episodes > 0
            and anilist_media_status == "FINISHED"
        ):
            # series completed watched
            logger.warning(
                f"[ANILIST] Emby episode watch count [{watched_episode_count}] was higher than the "
                f"one on AniList total episodes for that series [{anilist_total_episodes}] | updating "
                "AniList entry to completed"
            )

            update_episode_incremental(item, watched_episode_count, anilist_episodes_watched, "COMPLETED", token)
            return
        elif (
            watched_episode_count > anilist_episodes_watched
            and anilist_total_episodes > 0
        ):
            # episode watch count higher than emby
            new_status = status if status == "REPEATING" else "CURRENT"
            logger.warning(
                f"[ANILIST] Emby episode watch count [{watched_episode_count}] was higher than the one"
                f" on AniList [{anilist_episodes_watched}] which has total of {anilist_total_episodes} "
                f"episodes | updating AniList entry to {new_status}"
            )

            update_episode_incremental(item, watched_episode_count, anilist_episodes_watched, new_status, token)
            return

        elif watched_episode_count == anilist_episodes_watched:
            logger.info(
                "[ANILIST] Episodes watched was the same on AniList and Emby so skipping update"
            )
            return
        elif (
            anilist_episodes_watched > watched_episode_count
            and ANILIST_EMBY_EPISODE_COUNT_PRIORITY
        ):
            if watched_episode_count > 0:
                logger.info(
                    f"[ANILIST] Episodes watched was higher on AniList [{anilist_episodes_watched}] than on Emby [{watched_episode_count}] "
                    "however Emby episode count override is active so updating"
                )

                # Since AniList episode count is higher we don't loop thru
                # updating the notification feed and just set the AniList
                # episode count once
                update_item(series.anilist_id, watched_episode_count, "CURRENT", token)
                return
            else:
                logger.info(
                    f"[ANILIST] Episodes watched was higher on AniList [{anilist_episodes_watched}] than "
                    f"on Emby [{watched_episode_count}] with Emby episode count override active however "
                    "Emby watched count is 0 so skipping update"
                )
        elif anilist_episodes_watched > watched_episode_count:
            logger.info(
                f"[ANILIST] Episodes watched was higher on AniList [{anilist_episodes_watched}] than on Emby [{watched_episode_count}] so skipping update"
            )
        elif anilist_total_episodes <= 0:
            logger.info(
                "[ANILIST] AniList total episodes was 0 so most likely invalid data"
            )


def update_episode_incremental(series: AnilistItem, watched_episode_count: int, anilist_episodes_watched: int, new_status: str, token: str):
    # calculate episode difference and iterate up so activity stream lists
    # episodes watched if episode difference exceeds 32 only update most
    # recent as otherwise will flood the notification feed
    episode_difference = watched_episode_count - anilist_episodes_watched
    if episode_difference > 32:
        update_item(series.anilist_id, watched_episode_count, new_status, token)
    else:
        for current_episodes_watched in range(anilist_episodes_watched + 1, watched_episode_count + 1):
            update_item(series.anilist_id, current_episodes_watched, new_status, token)


def retrieve_season_mappings(title: str, season: int) -> List[AnilistCustomMapping]:
    season_mappings: List[AnilistCustomMapping] = []

    # print(title)
    # print(season)

    if CUSTOM_MAPPINGS and title.lower() in CUSTOM_MAPPINGS:
        season_mappings = CUSTOM_MAPPINGS[title.lower()]
        # filter mappings by season
        season_mappings = [e for e in season_mappings if e.season == season]

    return season_mappings


def map_watchcount_to_seasons(title: str, season_mappings: List[AnilistCustomMapping], watched_episodes: int) -> Dict[int, int]:
    # mapping from anilist-id to watched episodes
    episodes_in_anilist_entry: Dict[int, int] = {}
    total_mapped_episodes = 0
    season = season_mappings[0].season

    for mapping in season_mappings:
        if watched_episodes >= mapping.start:
            episodes_in_season = (watched_episodes - mapping.start + 1)
            total_mapped_episodes += episodes_in_season
            episodes_in_anilist_entry[mapping.anime_id] = episodes_in_season

    if total_mapped_episodes < watched_episodes:
        logger.warning(
            f"[ANILIST] Custom mapping is incomplete for {title} season {season}. "
            f"Watch count is {watched_episodes}, but number of mapped episodes is {total_mapped_episodes}"
        )

    return episodes_in_anilist_entry


def clean_title(title: str) -> str:
    return re.sub("[^A-Za-z0-9]+", "", title.lower().strip())
