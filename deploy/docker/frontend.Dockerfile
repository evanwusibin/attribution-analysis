FROM nginx:1.27-alpine
COPY deploy/docker/frontend.nginx.conf /etc/nginx/conf.d/default.conf
COPY frontend /usr/share/nginx/html
EXPOSE 80
