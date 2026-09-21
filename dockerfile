# 1. Immagine base snella Python 3.11
FROM python:3.11-slim

# 2. Ottimizzazioni runtime Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 3. Directory di lavoro
WORKDIR /app

# 4. Installazione dipendenze leggere (nessuna compilazione C/CUDA)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copia sorgenti applicativi e catalogo dati
COPY app/ ./app/
COPY data/ ./data/
COPY static/ ./static/
COPY app.py .

# 6. Esposizione porta servizio
EXPOSE 8000

# 7. Healthcheck container
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# 8. Avvio con Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]