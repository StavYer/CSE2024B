from flask import Flask, jsonify, request
import requests
import google.generativeai as genai


app = Flask(__name__)
port = 8000
genai.configure(api_key="Insert API key here")
model = genai.GenerativeModel('gemini-pro')

REQUIRED_FIELDS =  ["title", "ISBN", "genre", "authors", "publisher", "publishedDate", "language",
                                     "summary", "id"]
GENRES = ["Fiction", "Children", "Biography", "Science", "Science Fiction", "Fantasy", "Other"]


class BookClub:
    def __init__(self):
        # lists of dicts, each dicts specifies a JSON object as required, either book or rating of that book
        self.books = []
        self.bookRatings = []
        self.ID = 0

    # Methods specify operations on books
    # Both add_book and add_book_rating should receive a JSON object!

    def add_book(self, book):
        return self.books.append(book)

    def add_book_rating(self, rating):
        return self.bookRatings.append(rating)

    def get_books(self):
        return self.books

    def get_book_ratings(self):
        return self.bookRatings

    def get_book(self, book_id):
        return next((book for book in self.books if book['id'] == book_id), None)

    def get_book_rating(self, book_id):
        return next((rating for rating in self.bookRatings if rating['id'] == book_id), None)

    def delete_book(self, book_id):
        book = self.get_book(book_id)
        if book is not None:
            self.books.remove(book)

    def update_book(self, book_id, updated_book):
        book = self.get_book(book_id)
        if book:
            book.update(updated_book)  # book should be a dict!

    # Should only be used if we're deleting a book from the collection!
    def delete_book_rating(self, book_id):
        rating = self.get_book_rating(book_id)
        if rating is not None:
            self.bookRatings.remove(rating)

    # Each of the validation methods should receive a JSON object!
    # Should be called before update_book() or add_book()!
    def validate_book_addition(self, book_payload):
        required_fields = REQUIRED_FIELDS[:3]
        genres = GENRES

        if len(book_payload) != 3 or not all([field in book_payload for field in required_fields]) \
                or not all([isinstance(book_payload[field], str) for field in required_fields]):
            return jsonify({"error": "Unprocessable content - check validity of fields"}), 422

        if len(book_payload["ISBN"]) != 13:
            return jsonify({"error": "Invalid ISBN"}), 422

        if book_payload["genre"] not in genres:
            return jsonify({"error": "Invalid genre"}), 422

        if any(book["ISBN"] == book_payload["ISBN"] for book in book_club.get_books()):
            return jsonify({"error": "A book with this ISBN already exists"}), 422
        return None

    def validate_book_update(self, book_payload):
        required_fields = REQUIRED_FIELDS
        genres = GENRES

        if (len(book_payload) != 9 or not all([field in book_payload for field in required_fields])
                or not isinstance(book_payload['language'], list) or not all([isinstance(book_payload[field], str)
                                                                              for field in required_fields
                                                                              if field != "language"])):
            return jsonify({"error": "Unprocessable content - check validity of fields"}), 422

        if book_payload["genre"] not in genres:
            return jsonify({"error": "Invalid genre"}), 422

        if len(book_payload["ISBN"]) != 13:
            return jsonify({"error": "Invalid ISBN"}), 422
        return None

    def validate_rating_for_a_book(self, rating_payload):
        if len(rating_payload) != 1 or 'value' not in rating_payload or not isinstance(rating_payload['value'], int) or  rating_payload['value'] < 1 or \
                rating_payload['value'] > 5:
            return jsonify({'error': 'Invalid rating value'}), 422
        return None

    def increment_id(self):
        self.ID += 1
        return self.ID


book_club = BookClub()  # Start a book club instance to store the books and ratings.


class Books:  # Represents the endpoint /books

    # GET gets a list of books, optionally filtered by parameters.
    # Returns a JSON of that list and a status code of 200, or 422 if request can't be processed
    def get(self):
        request_parameters = request.args
        filtered_books = book_club.get_books()
        for field, value in request_parameters.items():
            if field not in REQUIRED_FIELDS or (field == "genre" and value not in GENRES):
                return jsonify({"error": "Invalid field or genre"}), 422
            if field == "language":
                if value not in ['heb', 'eng', 'spa', 'chi']:
                    return jsonify({'error':'Invalid language'}), 422
                filtered_books = [book for book in filtered_books if value in book['language']]
            else:
                filtered_books = [book for book in filtered_books if book[field] == value]
        return jsonify(filtered_books), 200

    # POST creates a new book resource in /books, unless one already exists or there is a problem with the request.
    # Returns the id of the newly created book, as well as a status code of 201.
    # Also creates a new rating resource, with the same id as the book's.
    def post(self):

        # Get the payload and handle different errors
        book_payload = request.get_json()

        if not book_payload:
            return jsonify({"error": "Unsupported media type"}), 415

        error = book_club.validate_book_addition(book_payload)
        if error is not None:
            return error

        # We now get relevant details from the Google Books API, OpenLibrary API and Google Gemini API.
        book_details = self.get_book_details(book_payload['ISBN'])
        if book_details is None:
            return jsonify({"error": "Unable to connect to Google Books"}), 500

        book_language = self.get_book_language(book_payload['ISBN'])
        book_summary = self.get_book_summary(book_payload['title'], book_details['authors'])
        if book_summary is None:
            return jsonify({"error": "Unable to connect to Google Gemini"}), 500

        # We create the book ID, a book JSON object, and add it and a relevant rating JSON object to book club.
        # We return the book ID and a status code of 201.
        book_id = str(book_club.increment_id())
        book = {
            'title': book_payload['title'],
            'ISBN': book_payload['ISBN'],
            'genre': book_payload['genre'],
            'authors': book_details['authors'],
            'publisher': book_details['publisher'],
            'publishedDate': book_details['publishedDate'],
            'language': book_language,
            'summary': book_summary,
            'id': book_id
        }
        book_club.add_book(book)
        book_club.add_book_rating({'id': book_id, 'values': [], 'average': 0, 'title': book['title']})

        return jsonify({'id': book_id}), 201

    # Method to get the authors, publisher and publishedDate fields from the Google books api.
    @staticmethod
    def get_book_details(isbn):
        # Query the Google books api for a respone
        google_books_url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
        response = requests.get(google_books_url)
        if response.status_code == 200:
            book_data = response.json()
            if book_data['totalItems'] > 0:
                # we access a dictionary
                info = book_data['items'][0]['volumeInfo']
                # we get the authors field. If there are more than 1, we concatenate. Else, we put "missing".
                authors = info.get("authors", "missing")
                if len(authors) > 1:
                    authors = ' and '.join(info['authors'])
                else:
                    authors = authors[0]
                publisher = info.get("publisher", "missing")
                # we get the published date. If there isn't any, we put missing. if it's not in the required format,
                # we put missing.
                published_date = info.get("publishedDate", "missing")
                if len(published_date) == 4:
                    published_date = published_date
                elif len(published_date) != 10:
                    published_date = "missing"
                # we return a JSON representation (using a dict)
                return {
                    'authors': authors,
                    'publisher': publisher,
                    'publishedDate': published_date
                }

        return None

    # Method to get the relevant book languages from the OpenLibrary API. Returns a list of Languages.
    # If there is a problem contacting the API or the 'language' section in the API is empty, we return ['missing'].
    @staticmethod
    def get_book_language(isbn):
        open_library_url = f"https://openlibrary.org/search.json?q={isbn}&fields=key,title,author_name,language"
        response = requests.get(open_library_url)
        if response.status_code == 200:
            data = response.json()
            if data['numFound'] > 0:
                languages = data['docs'][0].get('language', ['missing'])
                return languages
        return ['missing']

    # Method to get a book summary generation from Google Gemini API
    @staticmethod
    def get_book_summary(title, authors):
        prompt = f"Summarize the book {title} by {authors} in 5 sentences or less."
        response = model.generate_content(prompt)
        if response.parts:
            return response.text
        return None


class SpecificBook:  # Represents the endpoint /books/{id}
    # GET retrieves a book with the provided id from /books/{id}, or returns an error if the book is not in
    # the collection.
    def get(self, book_id):
        book = book_club.get_book(book_id)
        if book is None:
            return jsonify({'error': 'Book not found'}), 404
        return jsonify(book), 200

    # DELETE deletes a book and rating associated with the provided book id from /books/{id} and /ratings/{id},
    # or returns an error if the book is not in the collection.
    def delete(self, book_id):
        book = book_club.get_book(book_id)
        if book is None:
            return jsonify({'error': 'Book not found'}), 404
        book_club.delete_book(book_id)
        book_club.delete_book_rating(book_id)
        return jsonify(book_id), 200

    # PUT updates the contents of a specific book JSON object in /books/{id}. If the book doesn't exist, or the request
    # media format isn't JSON, it returns an error. If the request parameters aren't valid according to BooksClub,
    # it returns an error.
    def put(self, book_id):
        book = book_club.get_book(book_id)
        if book is None:
            return jsonify({'error': 'Book not found'}), 404

        book_payload = request.get_json()

        if not book_payload:
            return jsonify({"error": "Unsupported media type"}), 415

        error = book_club.validate_book_update(book_payload)
        if error is not None:
            return error

        # if the request to update is valid and acceptable, we update the book with the requested id as needed.
        updated_book = {
            'title': book_payload['title'],
            'ISBN': book_payload['ISBN'],
            'genre': book_payload['genre'],
            'authors': book_payload['authors'],
            'publisher': book_payload['publisher'],
            'publishedDate': book_payload['publishedDate'],
            'language': book_payload['language'],
            'summary': book_payload['summary']
        }
        book_club.update_book(book_id, updated_book)

        return jsonify({'id': book_id}), 200


class Ratings:  # Represents the endpoint /ratings
    # GET  retrieves the ratings for all the current books in the server. It can be filtered by specifying an id in the
    # query string.
    def get(self):
        request_parameters = request.args
        filtered_ratings = book_club.get_book_ratings()
        # we filter ratings if we received a query for a specific id
        for field, value in request_parameters.items():
            if field == "id":
                filtered_ratings = [rating for rating in filtered_ratings if rating["id"] == value]
        return jsonify(filtered_ratings), 200


class SpecificRatings:  # Represents the endpoint /ratings/{id}
    # GET retrieves a specific rating, and if not found, returns an error.
    def get(self, book_id):
        rating = book_club.get_book_rating(book_id)
        if rating is None:
            return jsonify({'error': 'Rating not found'}), 404
        return jsonify(rating), 200


class SpecificRatingsValues:  # Represents the endpoint /ratings/{id}/values
    # POST allows the user to add a rating to a book in the server. It checks if the request is valid and acceptable,
    # and appropriate according to BooksClub.
    def post(self, book_id):
        rating = book_club.get_book_rating(book_id)
        if rating is None:
            return jsonify({'error': 'Rating not found'}), 404

        rating_payload = request.get_json()
        if not rating_payload:
            return jsonify({'error': 'Unsupported media type'}), 415

        error = book_club.validate_rating_for_a_book(rating_payload)
        if error is not None:
            return error

        rating['values'].append(rating_payload['value'])
        rating['average'] = sum(rating['values']) / len(rating['values'])

        return jsonify({'average': rating['average']}), 200


class TopBooks:  # Represents the endpoint /top
    # GET computes the books with the top 3 scores, and returns it. Note - it can be more than 3 books.
    def get(self):
        # Find books that have more than 3 ratings and sort them by average in descending order
        eligible_books = [book for book in book_club.books if
                          len(book_club.get_book_rating(book['id'])['values']) >= 3]
        sorted_books = sorted(eligible_books, key=lambda book: book_club.get_book_rating(book['id'])['average'],
                              reverse=True)

        # Add all books that have the top 3 highest ratings to the top books list
        top_books = []
        top_rate_counter = 0
        current_average = 0
        for book in sorted_books:
            if book_club.get_book_rating(book['id'])['average'] != current_average:
                top_rate_counter += 1
                if top_rate_counter > 3:  # If we have passed over all the books with the top 3 ratings
                    break
            top_books.append({'id': book['id'], 'title': book['title'],
                              'average': book_club.get_book_rating(book['id'])['average']})
            current_average = book_club.get_book_rating(book['id'])['average']

        return jsonify(top_books), 200

# Using flask to route appropriate HTTP requests to appropriate classes and methods.


@app.route('/books', methods=['GET', 'POST'])
def handle_books():
    if request.method == 'GET':
        return Books().get()
    elif request.method == 'POST':
        return Books().post()


@app.route('/books/<book_id>', methods=['GET', 'PUT', 'DELETE'])
def handle_book(book_id):
    if request.method == 'GET':
        return SpecificBook().get(book_id)
    elif request.method == 'PUT':
        return SpecificBook().put(book_id)
    elif request.method == 'DELETE':
        return SpecificBook().delete(book_id)


@app.route('/ratings', methods=['GET'])
def handle_ratings():
    return Ratings().get()


@app.route('/ratings/<book_id>', methods=['GET'])
def handle_rating(book_id):
    return SpecificRatings().get(book_id)


@app.route('/ratings/<book_id>/values', methods=['POST'])
def handle_rating_values(book_id):
    return SpecificRatingsValues().post(book_id)


@app.route('/top', methods=['GET'])
def handle_top_books():
    return TopBooks().get()


if __name__ == '__main__':
    app.run(port=port, host='0.0.0.0')
