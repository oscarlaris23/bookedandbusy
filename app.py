from flask import Flask, render_template, request, url_for, redirect, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import openai
import os
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
import secrets
from openai.error import RateLimitError


load_dotenv()
openai.api_key = os.environ.get("API_KEY")

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)  
print(f'Secret key: {app.secret_key}')
app.config["SESSION_TYPE"] = "filesystem"
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
db = SQLAlchemy(app)


class Reaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    book_title = db.Column(db.String(200), nullable=False)
    book_author = db.Column(db.String(200), nullable=False)
    is_liked = db.Column(db.Boolean, nullable=False)

    def __init__(self, user_id, book_title, book_author, is_liked):
        self.user_id = user_id
        self.book_title = book_title
        self.book_author = book_author
        self.is_liked = is_liked

        
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

    def __init__(self, username, password):
        self.username = username
        self.password = password

class UserPreference(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    preference = db.Column(db.String(200), nullable=False)

class UserGenre(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    genre_id = db.Column(db.Integer, db.ForeignKey('genre.id'), nullable=False)
class Genre(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)

    def __init__(self, name):
        self.name = name
def add_genres():
    genres = ["Action & Adventure", "Art & Photography", "Biography", "Business & Economics", "Comedy", "Computers & Internet", "Contemporary", "Cookbooks", "Crafts, Hobbies & Home", "Drama", "Dystopian", "Education & Teaching", "Environment & Nature", "Fantasy", "Fiction", "Graphic Novel", "Health & Wellness", "Historical Fiction", "History & Politics", "Horror", "Horror Fiction", "Humor & Satire", "Magical Realism", "Memoir", "Music & Entertainment", "Mystery", "Non-fiction", "Parenting & Families", "Paranormal Romance", "Philosophy", "Poetry", "Romance", "Satire", "Science & Technology", "Sci-Fi", "Self-Help", "Self-Help Books", "Spirituality", "Sports & Outdoors", "Thriller", "Travel & Adventure", "True Crime", "Women's Fiction", "Young Adult Fiction"]

    for genre_name in genres:
        genre = Genre.query.filter_by(name=genre_name).first()

        if genre is None:
            new_genre = Genre(name=genre_name)
            db.session.add(new_genre)

    db.session.commit()

      
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        add_genres() 
    app.run()



def chatcompletion(user_input, chat_history, selected_genres, selected_preferences):
    try:
        output = openai.ChatCompletion.create(
            model="gpt-3.5-turbo-0301",
            temperature=1,
            frequency_penalty=0,
            messages=[
                {"role": "system", "content": f"a book recommendation that keeps giving of recommendations without fail. do not say anything else besides the recommendation in the format asked, take into consideration the selected genres, prefrences and liked and disliked books. Selected genres: {', '.join(selected_genres)}; Selected preferences: {', '.join(selected_preferences)}. Conversation history: {chat_history}"},
                {"role": "user", "content": f"{user_input}"},
            ]
        )

        for item in output['choices']:
            chatgpt_output = item['message']['content']

        return chatgpt_output

    except RateLimitError as rate_limit_error:
        raise rate_limit_error

@app.errorhandler(openai.error.RateLimitError)
def handle_rate_limit_error(rate_limit_error):
    return render_template('error.html', error_message=str(rate_limit_error)), 500
    

@app.route('/')
def home():
    return render_template('home.html')



@app.route('/preferences_and_genres', methods=['GET', 'POST'])
@login_required
def preferences_and_genres():
    genres = Genre.query.all()
    preferences = ["Bestsellers", "Book-to-Movie Adaptations", "Children's Books", "Classics", "Graphic Novels", "New Releases", "Series", "Short Stories", "Underrated Gems", "Young Adult"]

    user_id = current_user.id

    if request.method == 'POST':
        selected_genres = [genre for genre in genres if request.form.get(f'genre_{genre.id}')]
        selected_preferences = [pref for pref in preferences if request.form.get(f'pref_{pref}')]

        # Store the selected genres and preferences in the session
        session['selected_genres'] = [genre.name for genre in selected_genres]
        session['selected_preferences'] = selected_preferences

        # Delete existing user preferences
        UserPreference.query.filter_by(user_id=user_id).delete()

        # Save new preferences
        for pref in selected_preferences:
            user_preference = UserPreference(user_id=user_id, preference=pref)
            db.session.add(user_preference)

        # Delete existing user genres
        UserGenre.query.filter_by(user_id=user_id).delete()

        # Save new genres
        for genre in selected_genres:
            user_genre = UserGenre(user_id=user_id, genre_id=genre.id)
            db.session.add(user_genre)

        db.session.commit()

    else:
        user_preferences = UserPreference.query.filter_by(user_id=user_id).all()
        selected_preferences = [user_preference.preference for user_preference in user_preferences]

        user_genres = UserGenre.query.filter_by(user_id=user_id).all()
        selected_genres = [Genre.query.get(user_genre.genre_id).name for user_genre in user_genres]

    return render_template('preferences_and_genres.html', genres=genres, preferences=preferences, selected_genres=selected_genres, selected_preferences=selected_preferences)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()
        if user and user.password == password:
            login_user(user)
            return redirect(url_for('home'))

        return render_template('login.html', error="Invalid username or password")

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if password != confirm_password:
            return render_template('register.html', error="Passwords do not match")

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            return render_template('register.html', error="Username is already taken")

        user = User(username, password)
        db.session.add(user)
        db.session.commit()

        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/recommendation', methods=['GET', 'POST'])
@login_required
def recommendation():
    user_id = current_user.id
    selected_genres = session.get('selected_genres', [])
    selected_preferences = session.get('selected_preferences', [])

    # Fetch liked and disliked books for the current user from the database
    liked_books = Reaction.query.filter_by(user_id=user_id, is_liked=True).all()
    disliked_books = Reaction.query.filter_by(user_id=user_id, is_liked=False).all()
    
    button_text = ''  # Initialize button_text with an empty string
    chat_history = ''  # Initialize chat_history with an empty string
    chat_history_html_formatted = ''  # Initialize chat_history_html_formatted with an empty string

    if request.method == 'POST':
        button_text = request.form.get('button_text')
        chat_history = request.form.get('history') or ''
        # Format liked and disliked books
        liked_books_formatted = "\n".join([f"Title: {book.book_title}\nAuthor: {book.book_author}" for book in liked_books])
        disliked_books_formatted = "\n".join([f"Title: {book.book_title}\nAuthor: {book.book_author}" for book in disliked_books])

        # Include liked and disliked books in the user input
        user_input = f"Selected genres: {', '.join(selected_genres)}; Selected preferences: {', '.join(selected_preferences)}."
        if liked_books_formatted:
            user_input += f"\nMy Liked books are:\n{liked_books_formatted}"
        if disliked_books_formatted:
            user_input += f"\nMy Disliked books are:\n{disliked_books_formatted}"

        user_input += "\nPlease provide exactly one book recommendation with an interesting description of 3-4 sentences in the following format, with each detail on a new line:\nTitle: [title]\nAuthor: [author]\nDescription: [Description]."

    if button_text == 'clear':
        chat_history = ''
        chat_history_html_formatted = ''

    if button_text == 'submit':
        chatgpt_output = chatcompletion(user_input, chat_history, selected_genres, selected_preferences)
        chat_history += f'\nUser: {user_input}\n'
        chat_history += f'{chatgpt_output}\n'
        chat_history_html_formatted = chat_history.replace('\n', '<br>')


    return render_template('recommendation.html', selected_genres=selected_genres, selected_preferences=selected_preferences, chat_history=chat_history, chat_history_html_formatted=chat_history_html_formatted)

@app.route('/history')
@login_required
def history():
    user_id = current_user.id
    liked_books = Reaction.query.filter_by(user_id=user_id, is_liked=True).all()
    disliked_books = Reaction.query.filter_by(user_id=user_id, is_liked=False).all()
    return render_template('history.html', liked_books=liked_books, disliked_books=disliked_books)

@app.route('/reaction', methods=['POST'])
def handle_reaction():
    user_id = current_user.id
    book_title = request.form.get('book_title')
    book_author = request.form.get('book_author')
    like = request.form.get('like') == 'true'
    reaction = Reaction(user_id, book_title, book_author, like)
    db.session.add(reaction)
    db.session.commit()

    return {'status': 'success'}, 200


@app.route('/delete_reaction', methods=['POST'])
def delete_reaction():
    book_id = request.form.get('book_id')
    reaction = Reaction.query.get(book_id)
    if reaction:
        db.session.delete(reaction)
        db.session.commit()
        return {'status': 'success'}, 200
    else:
        return {'status': 'error'}, 404

@app.route('/change_reaction/<int:book_id>')
def change_reaction(book_id):
    reaction = Reaction.query.get(book_id)
    if reaction:
        reaction.is_liked = not reaction.is_liked
        db.session.commit()
    return redirect(url_for('history'))

@app.route('/cart')
@login_required
def cart():
    user_id = current_user.id
    liked_books = Reaction.query.filter_by(user_id=user_id, is_liked=True).all()
    return render_template('cart.html', liked_books=liked_books, generate_amazon_link=generate_amazon_link)

def generate_amazon_link(book_title, book_author):
    base_url = "https://www.amazon.com/s?k="
    search_query = f"{book_title} {book_author}"
    search_query = search_query.replace(' ', '+')
    amazon_link = base_url + search_query
    return amazon_link

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        add_genres() 
    app.run()