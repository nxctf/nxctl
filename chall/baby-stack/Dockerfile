FROM debian:bookworm-slim

RUN apt update \
 && apt install -y socat \
 && apt clean \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY baby-stack .

RUN chmod +x baby-stack

EXPOSE 9001

CMD socat \
    TCP-LISTEN:9001,reuseaddr,fork \
    EXEC:"./baby-stack",pty,stderr,setsid,sigint,sane
