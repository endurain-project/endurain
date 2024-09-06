# Use an official node runtime as a parent image
FROM node:20-alpine as build-stage

# Links Docker image with repository
LABEL org.opencontainers.image.source https://github.com/joaovitoriasilva/endurain

# Set the working directory to /app
WORKDIR /app

# Copy package.json and package-lock.json first (this helps leverage Docker layer caching)
COPY app/package*.json ./

# Install app dependencies
RUN npm install --production

# Copy the rest of the application code into the container
COPY app ./

# Build the app
RUN npm run build

# Remove node_modules to reduce image size as it's not needed for the final image
RUN rm -rf node_modules

# Use nginx to serve the built app
FROM nginx:alpine as production-stage

# Copy the built app from the build stage
COPY --from=build-stage /app/dist /usr/share/nginx/html

# Copy the custom Nginx configuration
COPY nginx-custom.conf /etc/nginx/conf.d/default.conf

# Copy the frontend environment script and make it executable
COPY frontend_env.sh /docker-entrypoint.d/frontend_env.sh
RUN chmod +x /docker-entrypoint.d/frontend_env.sh

# Expose port 80 to the outside world
EXPOSE 80

# Environment variables for the frontend
ENV VITE_BACKEND_PROTOCOL=http
ENV VITE_BACKEND_HOST=localhost:98
ENV VITE_STRAVA_CLIENT_ID=changeme

# Start Nginx when the container starts
CMD ["nginx", "-g", "daemon off;"]