FROM python:3.12.2-slim

WORKDIR ./app

COPY Loan_Service.py .

RUN pip install flask requests pymongo

EXPOSE 80

CMD ["python3", "Loan_Service.py"]