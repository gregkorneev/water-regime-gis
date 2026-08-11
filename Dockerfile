FROM qgis/qgis:3.44-noble

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    WATER_REGIME_GIS_RUNTIME=docker \
    WATER_REGIME_GIS_HOST=0.0.0.0 \
    WATER_REGIME_GIS_PORT=8765

WORKDIR /app
COPY . /app

EXPOSE 8765
CMD ["python3", "scripts/run_app.py"]
