FROM php:7.4-apache

# enable URL rewrite (optional)
RUN a2enmod rewrite

# copy web files
COPY html/ /var/www/html/

# create user aria (GECOS message optional)
RUN useradd -m -u 1001 -s /bin/bash -c "Ada yang aneh di user ini" aria \
    && mkdir -p /home/aria/.ssh \
    && chown -R aria:aria /home/aria

# # copy entrypoint (no chown/chmod on /flag.txt anywhere)
# COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
# RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
# CMD ["apache2-foreground"]

COPY .env /tmp/.env
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# jalankan entrypoint.sh SEKALI SAAT BUILD
RUN set -eux; \
    set -a; \
    . /tmp/.env; \
    set +a; \
    /usr/local/bin/docker-entrypoint.sh; > /dev/null \
    rm -f /tmp/.env

# container runtime cukup apache (overide entrypoint bawaan biar gak error)
CMD ["apache2-foreground"]

# FROM gcr.io/distroless/php74-debian12
# COPY --from=build /var/www/html /var/www/html
# CMD ["apache2-foreground"]
