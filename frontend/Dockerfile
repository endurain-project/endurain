# Use an official node runtime as a parent image
FROM node:20-alpine as build-stage

# Links Docker image with repository
LABEL org.opencontainers.image.source https://github.com/joaovitoriasilva/endurain

# Set the working directory to /app
WORKDIR /app

# Copy package.json and package-lock.json
COPY app/package*.json ./
RUN npm install

# Copy the current directory contents into the container at /app
COPY app ./

# Build the app
RUN npm run build

# Use nginx to serve the built app
FROM nginx:alpine as production-stage

COPY --from=build-stage /app/dist /usr/share/nginx/html
COPY nginx-custom.conf /etc/nginx/conf.d/default.conf

COPY frontend_env.sh /docker-entrypoint.d/frontend_env.sh
RUN chmod +x /docker-entrypoint.d/frontend_env.sh

EXPOSE 80

ENV VITE_BACKEND_PROTOCOL=http
ENV VITE_BACKEND_HOST=localhost:98
ENV VITE_STRAVA_CLIENT_ID=changeme

CMD ["nginx", "-g", "daemon off;"]
