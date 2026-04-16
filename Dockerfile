FROM node:20-slim AS frontend
WORKDIR /app
COPY web/package*.json web/
RUN npm install --prefix web
COPY web/ web/
RUN npm run build --prefix web

FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=frontend /app/web/out ./static
EXPOSE 8000
CMD ["python", "main.py"]
