FROM node:26-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy application
COPY . .

# Run as the non-root user built into the node:alpine image (uid/gid 1000)
# rather than creating a new one, since that uid/gid is already taken.
RUN chown -R node:node /app
USER node

# Expose port
EXPOSE 5173

# Run development server
CMD ["npm", "run", "dev", "--", "--host"]
