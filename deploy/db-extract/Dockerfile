FROM alpine:3.20
RUN apk add --no-cache mariadb-client curl
COPY extract.sh /extract.sh
ENTRYPOINT ["/extract.sh"]
