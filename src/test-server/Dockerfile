
FROM python:3.9

WORKDIR /code

COPY ./requirements.txt /code/requirements.txt

RUN  apt-get update -y && apt-get install -y iputils-ping
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

COPY ./app /code/app

CMD ["uvicorn", "app.server:app", "--reload","--host", "0.0.0.0", "--port", "443", "--ssl-keyfile", "/code/app/key.pem", "--ssl-certfile", "/code/app/cert.pem"]