#Deriving the latest base image
FROM python:3.11 AS builder

COPY requirements.txt .
# install dependencies to the local user directory (eg. /root/.local)
RUN pip install --user --no-warn-script-location -r requirements.txt

FROM python:3.11-slim

WORKDIR /embyanisync

#to COPY the remote file at working directory in container
COPY ./ /embyanisync/

COPY --from=builder /root/.local /root/.local
RUN chmod -R a+rX /root

ENV PATH=/root/.local:$PATH
ENV PYTHONPATH=/root/.local/lib/python3.11/site-packages

#CMD instruction should be used to run the software
#contained by your image, along with any arguments.

CMD [ "python", "/embyanisync/EmbyAniSync.py"]