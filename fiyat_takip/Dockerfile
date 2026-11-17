FROM ghcr.io/home-assistant/base:latest

RUN apk add --no-cache python3 py3-pip py3-requests py3-beautifulsoup4 \
 && pip3 install --no-cache-dir --break-system-packages "telethon>=1.36,<2"

COPY takip.py grup.py urunler.json /app/

CMD [ "python3", "-u", "/app/takip.py" ]
