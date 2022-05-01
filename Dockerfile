FROM python:3.10
MAINTAINER Vladimir Prokofev <v@prokofev.me>

WORKDIR /backup

RUN pip install openstacksdk==0.61.0

COPY backup.py ./

CMD [ "python3", "./backup.py" ]
