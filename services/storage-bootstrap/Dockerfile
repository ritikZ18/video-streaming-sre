FROM python:3.12-alpine

RUN pip install --no-cache-dir boto3==1.40.76

COPY bootstrap.py /app/bootstrap.py

USER 65532:65532
ENTRYPOINT ["python", "/app/bootstrap.py"]
