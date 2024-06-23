from flask import Flask, jsonify, request
import requests
import pymongo
import os
import re
from datetime import datetime

app = Flask(__name__)
PORT = os.getenv('PORT', 80)
MONGO_URL = os.getenv('MONGO_URL', 'mongodb://mongo:27017/')

BOOKS_SERVICE_URL = os.getenv('BOOKS_SERVICE_URL', 'http://books_service:80/')
client = pymongo.MongoClient(MONGO_URL)
database = client["MongoDB"]
loan_collection = database["loans"]

REQUIRED_FIELDS = ["memberName", "ISBN", "loanDate", "title", "bookID", "loanID"]
GENRES = ["Fiction", "Children", "Biography", "Science", "Science Fiction", "Fantasy", "Other"]

# On * first * start of the service, we initialize a document to hold our id counter.
# We also try to prevent a potential race condition.
if loan_collection.find_one({"_id": 0}) is None:
    loan_collection.update_one(
        {"_id": 0},
        {"$setOnInsert": {"highest_object_id": 0}},
        upsert=True
    )


class LoansService:

    # Methods specify operations on Loans.

    # Should receive a JSON object. Adds it to the loan collection.
    def add_loan(self, loan):
        loan_collection.insert_one(loan)

    # Retrieves a loan from the collection by a specific id.
    # Note that we check that we do not return our counter document, and also drop the _id field for clarity.
    def get_loan(self, loan_id):
        if int(loan_id) > 0:
            return loan_collection.find_one({"_id": int(loan_id)}, {"_id": 0})

    def delete_loan(self, loan_id):

        loan_collection.delete_one({"_id": int(loan_id)})

    def get_loans(self):
        return list(loan_collection.find({"_id": {"$gt": 0}}, {"_id": 0}))

    def check_if_in_library(self, ISBN):
        return requests.get(f"{BOOKS_SERVICE_URL}/books?ISBN={ISBN}")

    def increment_id(self):
        current_key_doc_identifier = {"_id": 0}
        current_key = loan_collection.find_one(current_key_doc_identifier)["highest_object_id"] + 1
        loan_collection.update_one(current_key_doc_identifier, {"$set": {"highest_object_id": current_key}})
        return current_key

    def loan_count_of_member(self, member_name):
        return loan_collection.count_documents({"memberName": member_name})

    def validate_loan_addition(self, loan_payload):
        required_fields = REQUIRED_FIELDS[:3]

        if len(loan_payload) != len(required_fields) or not all([field in loan_payload for field in required_fields]):
            return jsonify({"error": "Unprocessable content - check validity of fields"}), 422

        if len(loan_payload["ISBN"]) != 13:
            return jsonify({"error": "Invalid ISBN"}), 422

        if any(loan["ISBN"] == loan_payload["ISBN"] for loan in self.get_loans()):
            return jsonify({"error": "This book is already on loan"}), 422
        member_name = loan_payload["memberName"]

        if self.loan_count_of_member(member_name) >= 2:
            return jsonify({"error": f"Too many books on loan for {member_name}."}), 422

        date_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')  # We check that the date-format is correct
        if not date_pattern.match(loan_payload["loanDate"]):
            return jsonify({"error": "Invalid date format, should be YYYY-MM-DD"}), 422
        else:
            try:
                datetime.strptime(loan_payload["loanDate"], '%Y-%m-%d')  # We check that the date itself is valid
            except ValueError:
                return jsonify({"error": "Invalid date"}), 422

        return None


loan_service = LoansService()


class Loans:  # Represents the endpoint /loans

    # GET gets a list of loans, optionally filtered by parameters (fields).
    # Returns a JSON of that list and a status code of 200, or 422 if request can't be processed
    def get(self):
        request_parameters = request.args
        filtered_loans = loan_service.get_loans()
        for field, value in request_parameters.items():
            if field not in REQUIRED_FIELDS:
                return jsonify({"error": "Unprocessable content - check validity of fields"}), 422

            filtered_loans = [loan for loan in filtered_loans if loan[field] == value]
        return jsonify(filtered_loans), 200

    def post(self):

        # Get the payload and handle different errors
        loan_payload = request.get_json()

        if not loan_payload:
            return jsonify({"error": "Unsupported media type"}), 415

        error = loan_service.validate_loan_addition(loan_payload)
        if error is not None:
            return error

        book_response = loan_service.check_if_in_library(loan_payload["ISBN"])
        book_details = book_response.json()
        if len(book_details) == 0 or book_response.status_code != 200:
            return jsonify({"error": "book not found in the library"}), 404
        print("book details: ", book_details)
        print("hi!")
        loan_id = loan_service.increment_id()
        loan = {
            '_id': loan_id,
            'loanID': str(loan_id),
            'bookID': book_details['id'],
            'title': book_details['title'],
            'ISBN': loan_payload['ISBN'],
            'memberName': loan_payload['memberName'],
            'loanDate': loan_payload['loanDate']
        }
        loan_service.add_loan(loan)

        return jsonify({'loanID': f"{loan_id}"}), 201


class SpecificLoan:  # Represents the endpoint /loans/{id}

    def get(self, loan_id):
        loan = loan_service.get_loan(loan_id)
        if loan is None:
            return jsonify({'error': 'Loan not found'}), 404
        return jsonify(loan), 200

    def delete(self, loan_id):
        loan = loan_service.get_loan(loan_id)
        if loan is None:
            return jsonify({'error': 'Loan not found'}), 404
        loan_service.delete_loan(loan_id)
        return jsonify(str(loan_id)), 200

# Using flask to route appropriate HTTP requests to appropriate classes and methods.


@app.route('/loans', methods=['GET', 'POST'])
def handle_loans():
    if request.method == 'GET':
        return Loans().get()
    elif request.method == 'POST':
        return Loans().post()


@app.route('/loans/<loan_id>', methods=['GET', 'DELETE'])
def handle_loan(loan_id):
    if request.method == 'GET':
        return SpecificLoan().get(loan_id)
    elif request.method == 'DELETE':
        return SpecificLoan().delete(loan_id)


if __name__ == '__main__':
    app.run(port=PORT, host='0.0.0.0')