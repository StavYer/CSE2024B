FROM python:3.12.2-slim

WORKDIR ./app

COPY Book_Service.py .

RUN pip install flask requests pymongo

EXPOSE 80

CMD ["python3", "Book_Service.py"]