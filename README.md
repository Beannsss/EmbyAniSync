# EmbyAniSync

This has since gone through a large re-design to have a bit of it's own identity from PlexAniSync. However, a lot of code is still used from the original project, including this readme. Credits to them.


## Setup

### Step 1 - Install Python

Make sure you have Python 3.10 or higher installed:

[Python homepage](https://www.python.org/)

### Step 2 - Download Project Files

Get the latest version using your favorite git client or by downloading the latest release from here:

https://github.com/Beannsss/EmbyAniSync/archive/master.zip

### Step 3 - Configuration

From the project directory rename `settings.ini.example` to `settings.ini`, open `settings.ini` with your favorite text editor and edit where needed.

#### Emby

Add in your anime section id (open library in browser and it should be there under "parentId") as well as your url and apikey that you created in emby dashboard.

URL should be {protocol}://{domain/ip}:{port}/emby. I don't think this actually needs /emby, but that's how it is documented in their api explorer.

```
[EMBY]
# Comma Seperated List of library ID for update_all
anime_section_ids = 1,2
url = https://example.domain.org/emby
apikey = EMBY_APIKEY_HERE
```

#### AniList

I went with a multi-user approach, you can create a subsection under users to specify anilist username and token on a per-user basis. This is subject to change if I find a less hacky way of doing this... Might be a toml angle.

For AniList you need get a so called `access_token` which you can retrieve via this link and if not logged in will ask you to do so:

https://anilist.co/api/v2/oauth/authorize?client_id=12485&response_type=token

Make sure to copy the entire key as it is pretty long and paste that in the settings file under 'access_token', no need to enclose it just paste it as-is.

*IMPORTANT:* To find your EMBY_USER_ID, go to the individual user's settings page and you will find it in the url.

Also, make sure you don't use email for anilist_username.

```
[users]
# Comma Seperated List of EMBY User Names (not sure if case sensitive) Corresponds to following subsections
users = Bob,Billy
[users.Bob]
emby_user_id = EMBY_USER_ID_HERE
anilist_username = ANILIST_USERNAME_HERE
anilist_token = ANILIST_TOKEN_HERE
[users.Billy]
emby_user_id = EMBY_USER_ID_HERE
anilist_username = ANILIST_USERNAME_HERE
anilist_token = ANILIST_TOKEN_HERE
```

### Step 4 - Install requirements


Install the addtional requirements using the Python package installer (pip) from within the project folder:

`pip install -r requirements.txt`

For advanced users, it is ideal to do this in a virtual environment, here is an example of what you can do before the pip install to install in a venv. This may not be 100% on point, but I'll edit later :)

If you install reqs in a venv, make sure you either have the venv activated when you run, or specifically use the python executable in the venv.

#### Windows

```
python -m venv venv
./venv/Lib/activate
```

#### Linux

```
python -m venv venv
source ./venv/bin/activate
```


### Step 5 - Start Syncing


Now that configuration is finished and requirements have been installed we can finally start the sync script:

`python EmbyAniSync.py`

or 

`./venv/Scripts/python EmbyAniSync.py`

This will run an initial sync of everything, start a flask server to open up an endpoint for emby to send a webhook POST, and schedule a full sync every 4 hours (configurable in the future :))


### Step 6 - Webhook

Using Emby Webhooks, we are able to sync a season as soon as we are done watching.

Basic usage of this feature, more detailed instructions to come.

#### Configure Webhook

In Emby dashboard, you can create a webhook that points to your flask app:port/update_show, and sends on "Playback Stop" and "Mark Played"

![image](https://user-images.githubusercontent.com/8314499/236054014-eec29591-7b93-4102-ad7c-956b58ee9660.png)

### Step 7(a) - Run as a service Systemd (Linux)

Enter the following command into your terminal to create a new service file. 
replacing nano with your preferred text editor

```bash
sudo nano /etc/systemd/system/embyanisync.service
```

Paste the contents of the following into the new file
replacing the `/opt/EmbyAniSync/` and `#USER#` with the correct ones for your install

```bash
[Unit]
Description=EmbyAniSync
After=multi-user.target
[Service]
Type=idle
Restart=on-failure
User=#USER#
ExecStart=/bin/bash -c 'cd /opt/EmbyAniSync/ && python3 EmbyAniSync.py'
[Install]
WantedBy=multi-user.target
```

Then run the following commands to start the service and enable it at boot

#### Reload the daemon for the latest files
```bash
sudo systemctl daemon-reload
```

#### Start the Service
```bash
sudo systemctl start embyanisync
```

#### Check the service is running
```bash
sudo systemctl status embyanisync
```

#### Enable at boot
```bash
sudo systemctl enable embyanisync
```
### Step 7(b) - Run as a service NSSM (Windows)

Download NSSM from the [official website](https://nssm.cc/). NSSM is used to create a windows service to run the script.

Once downloaded, copy `nssm.exe` to the same directory the script is located in. 

Next, open cmd in that directory with administrator privileges.

In cmd, enter the following command:

```
nssm install AniSync
```

You can replace `AniSync` with a name of your choice but remember to replace any instances of `AniSync` in the following commands with your choice.

Next, enter the following command:

```
nssm edit AniSync
```

This will open up a GUI interface. Enter the details as follows:

- Path: `path\to\your\python.exe`
- Startup Directory: `path\to\your\EmbyAniSync\directory`
- Arguments: `"path\to\EmbyAniSync.py"`

![Screenshot 2024-08-10 123852](https://github.com/user-attachments/assets/2dd48117-ca08-4031-b4fc-8d149749930a)

**Note:**
- Path to your Startup Directory is the same directory where `EmbyAniSync.py` is located.
- Arguments should include the quotation marks (""). 

Next click on the details tab and make sure `Startup type` is set to `Automatic`.

![Screenshot 2024-08-10 132317](https://github.com/user-attachments/assets/98654585-44f7-4c30-b662-3047ae864815)

Next, click on `Edit Service`.

Finally, enter the following command in cmd:

```
nssm restart AniSync
```

#### Optional - Create logs

You can create logs for the service. This can be helpful to debug any issues.

First create a directory to save your log files. Ideally you can create this directory in the same directory as your script.

```
.
└── EmbyAniSync/
    ├── embypython/
    ├── logs/
    ├── EmbyAniSync.py
    └── nssm.exe
```

Next, open up cmd as administrator in the same directory that EmbyAniSync.py is located.

Enter the following command:

```
nssm edit AniSync
```

Now, in the NSSM GUI, click on the `I/O` tab. You may need to click on the arrow buttons to navigate to it.

- In `Output (stdout)` enter the following:
    
    `path\to\the\log\directory\service.log`

- In `Error (stderr)` enter the following:

    `path\to\the\log\directory\service-debug.log`

![Screenshot 2024-08-10 125554](https://github.com/user-attachments/assets/3f47ddd7-3fdb-4eb8-9381-ece09c95e7e9)

Next, click on `Edit Service`.

Finally, enter the following command in cmd:

```
nssm restart AniSync
```

## Optional features 

All of this is copied over from the Parent Project so not 100% sure if accurate here.

### Custom anime mapping

You can manually link a Emby title and season to an AniList ID, to do so:

- From the project folder copy `custom_mappings.yaml.example` to `custom_mappings.yaml`
- Add new entries there in the following format:

```yaml
  - title: "Emby title for series"
    seasons:
      - season: Emby season
        anilist-id: AniList series ID
      - season: Emby season
        anilist-id: AniList series ID
```

If the Emby season should be split into 2 seasons, add an optional `start` parameter to each season like this:

```yaml
  - title: "Re:ZERO -Starting Life in Another World-"
    seasons:
      - season: 2
        anilist-id: 108632
        start: 1
      - season: 2
        anilist-id: 119661
        start: 14
```

Episodes 1-13 will be mapped to Re:Zero 2nd Season Part 1, episodes 14 and higher will be mapped to Re:Zero 2nd Season Part 2.

- To find out the AniList ID you can visit the series page and copy it from the site url, like for example My Shield hero has ID 99263:

https://anilist.co/anime/99263/Tate-no-Yuusha-no-Nariagari

- You can remove any existing entries from the example file as they are purely instructional
- Upon startup it will check if the file is a valid YAML file. The most likely reason it's not is because you didn't put quotes around an anime title with special characters (e.g. ":") in it.

#### Community mappings

There are some mappings provided by the Github community at https://github.com/RickDB/EmbyAniSync-Custom-Mappings/. You can use them by specifying `remote-urls` like in the example mapping file.

If the local mapping file contains mappings for the same show as the community mapping, the local one will take precedence.

The feature of synonyms was introduced for the community mappings where you can specify that a show can have one of multiple titles but should be mapped the same way. See Shaman King (2021) in the example mapping file.

### Custom settings file location

If you want to load a different settings.in file you can do so by supplying it in the first argument like so:

`python EmbyAniSync.py settings_alternate.ini`

In case of the Tautulli sync helper script you can do as well, first argument will then be settings filename and second will be the series name like so:

`python TautulliSyncHelper.py  settings_alternate.ini <Emby show name>`

### Make Emby watched episode count take priority

By default if AniList episode count watched is higher than that of Emby it will skip over, this can be overriden with the setting `Emby_episode_count_priority`

When set to True it will update the AniList entry if Emby watched episode count is higher than 0 and will not take into account the AniList watched episode count even if that is higher.

**Use this with caution as normally this isn't required and only meant for certain use cases.**

## Support

https://github.com/Beannsss/EmbyAniSync/issues


## Planned

- 3.7 compatibility if it is desired. I like a lot of 3.8->3.10 features so I decided to require 3.10
- Jellyfin Support?

## Credits


[PlexAniSync](https://github.com/RickDB/PlexAniSync) for Original Idea, and much of the code in this repo (notably the anilist side of things)

[Emby](https://emby.media/)

[EmbyPython SDK](https://dev.emby.media/home/sdk/apiclients/Python/README.html)
