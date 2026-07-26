FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Generates the physics-simulated dataset at image build time so the
# container starts ready to serve (NFR-12: runs air-gapped, no external
# calls needed at inference time).
RUN python -m app.simulation.physics_simulator

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
