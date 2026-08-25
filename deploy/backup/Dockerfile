# A one-off container that dumps the database to a blob URL, or restores from one.
# Same mysql image as the server, so mysqldump and mysql match the database exactly.
FROM mysql:5.7.41
COPY --from=curlimages/curl:8.11.1 /usr/bin/curl /usr/local/bin/curl
COPY dump.sh restore.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/dump.sh /usr/local/bin/restore.sh
ENTRYPOINT []
CMD ["dump.sh"]
