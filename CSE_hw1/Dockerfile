FROM python:3.12.2-slim

WORKDIR /app

COPY Book_club.py .

RUN pip install flask requests google.generativeai

EXPOSE 8000

CMD ["python3", "Book_club.py"]