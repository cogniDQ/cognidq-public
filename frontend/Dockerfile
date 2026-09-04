FROM node:18-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy application
COPY . .

# Run as a non-root user. UID/GID 1000 matches the default first non-root
# user on most Linux hosts, which keeps bind-mount permissions sane in
# docker-compose dev usage (mirrors backend/Dockerfile).
RUN addgroup -g 1000 appuser \
    && adduser -D -u 1000 -G appuser appuser \
    && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 5173

# Run development server
CMD ["npm", "run", "dev", "--", "--host"]
