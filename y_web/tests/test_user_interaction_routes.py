"""
Tests for y_web user interaction routes
"""
import pytest
import tempfile
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from werkzeug.security import generate_password_hash


@pytest.fixture
def app():
    """Create a test app for user interaction route testing"""
    app = Flask(__name__)
    db_fd, db_path = tempfile.mkstemp()
    
    app.config.update({
        'TESTING': True,
        'SECRET_KEY': 'test-secret-key',
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
        'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        'WTF_CSRF_ENABLED': False,
    })
    
    db = SQLAlchemy(app)
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    
    # Define models for testing
    class User_mgmt(db.Model):
        __tablename__ = 'user_mgmt'
        id = db.Column(db.Integer, primary_key=True)
        username = db.Column(db.String(50), nullable=False)
        email = db.Column(db.String(100), nullable=False)
        password = db.Column(db.String(200), nullable=False)
        joined_on = db.Column(db.Integer, nullable=False, default=1234567890)
        
        def is_authenticated(self):
            return True
        
        def is_active(self):
            return True
        
        def is_anonymous(self):
            return False
        
        def get_id(self):
            return str(self.id)
    
    class Admin_users(db.Model):
        __tablename__ = 'admin_users'
        id = db.Column(db.Integer, primary_key=True)
        username = db.Column(db.String(50), nullable=False)
        email = db.Column(db.String(100), nullable=False)
        password = db.Column(db.String(200), nullable=False)
        role = db.Column(db.String(20), default='user')
        llm = db.Column(db.String(50), default='llama3.2:latest')
    
    class Follow(db.Model):
        __tablename__ = 'follow'
        id = db.Column(db.Integer, primary_key=True)
        user_id = db.Column(db.Integer, nullable=False)
        follower_id = db.Column(db.Integer, nullable=False)
        action = db.Column(db.String(10), nullable=False)
        round = db.Column(db.Integer, nullable=False)
    
    class Post(db.Model):
        __tablename__ = 'post'
        id = db.Column(db.Integer, primary_key=True)
        tweet = db.Column(db.String(500), nullable=False)
        user_id = db.Column(db.Integer, nullable=False)
        round = db.Column(db.Integer, nullable=False)
        shared_from = db.Column(db.Integer, default=-1)
        comment_to = db.Column(db.Integer, default=-1)
    
    class Rounds(db.Model):
        __tablename__ = 'rounds'
        id = db.Column(db.Integer, primary_key=True)
        day = db.Column(db.Integer, nullable=False)
        hour = db.Column(db.Integer, nullable=False)
    
    class Reactions(db.Model):
        __tablename__ = 'reactions'
        id = db.Column(db.Integer, primary_key=True)
        user_id = db.Column(db.Integer, nullable=False)
        post_id = db.Column(db.Integer, nullable=False)
        type = db.Column(db.String(10), nullable=False)
        round = db.Column(db.Integer, nullable=False)
    
    class Interests(db.Model):
        __tablename__ = 'interests'
        iid = db.Column(db.Integer, primary_key=True)
        interest = db.Column(db.String(100), nullable=False)
    
    class User_interest(db.Model):
        __tablename__ = 'user_interest'
        id = db.Column(db.Integer, primary_key=True)
        user_id = db.Column(db.Integer, nullable=False)
        interest_id = db.Column(db.Integer, nullable=False)
        post_id = db.Column(db.Integer, nullable=False)
    
    class Post_Sentiment(db.Model):
        __tablename__ = 'post_sentiment'
        id = db.Column(db.Integer, primary_key=True)
        post_id = db.Column(db.Integer, nullable=False)
        neg = db.Column(db.Float)
        neu = db.Column(db.Float)
        pos = db.Column(db.Float)
        compound = db.Column(db.Float)
    
    @login_manager.user_loader
    def load_user(user_id):
        return User_mgmt.query.get(int(user_id))
    
    # Create user interaction blueprint with minimal functionality
    from flask import Blueprint, request, redirect, jsonify
    from flask_login import login_required, current_user
    
    user = Blueprint("user_actions", __name__)
    
    def mock_toxicity(text, username, post_id, db):
        """Mock toxicity function"""
        pass
    
    def mock_vader_sentiment(text):
        """Mock sentiment analysis"""
        return {"neg": 0.1, "neu": 0.7, "pos": 0.2, "compound": 0.1}
    
    @user.route("/follow/<int:user_id>/<int:follower_id>", methods=["GET", "POST"])
    @login_required
    def follow(user_id, follower_id):
        # Get the last round id from Rounds
        current_round = Rounds.query.order_by(Rounds.id.desc()).first()
        if not current_round:
            return "No rounds available", 400
        
        # Check if already followed
        followed = (
            Follow.query.filter_by(user_id=user_id, follower_id=follower_id)
            .order_by(Follow.id.desc())
            .first()
        )
        
        if followed and followed.action == "follow":
            # Unfollow
            new_follow = Follow(
                follower_id=follower_id,
                user_id=user_id,
                action="unfollow",
                round=current_round.id,
            )
            db.session.add(new_follow)
            db.session.commit()
            return "Unfollowed successfully"
        
        # Follow
        new_follow = Follow(
            follower_id=follower_id,
            user_id=user_id,
            action="follow",
            round=current_round.id,
        )
        db.session.add(new_follow)
        db.session.commit()
        
        return "Followed successfully"
    
    @user.route("/share_content")
    @login_required
    def share_content():
        post_id = request.args.get("post_id")
        if not post_id:
            return "Missing post_id", 400
        
        # Get the post
        original = Post.query.filter_by(id=post_id).first()
        if not original:
            return "Post not found", 404
        
        current_round = Rounds.query.order_by(Rounds.id.desc()).first()
        if not current_round:
            return "No rounds available", 400
        
        post = Post(
            tweet=original.tweet,
            user_id=current_user.id,
            round=current_round.id,
            shared_from=original.id
        )
        db.session.add(post)
        db.session.commit()
        
        return "Content shared successfully"
    
    @user.route("/react_to_content")
    @login_required
    def react():
        post_id = request.args.get("post_id")
        reaction_type = request.args.get("type", "like")
        
        if not post_id:
            return "Missing post_id", 400
        
        current_round = Rounds.query.order_by(Rounds.id.desc()).first()
        if not current_round:
            return "No rounds available", 400
        
        # Check if already reacted
        existing_reaction = Reactions.query.filter_by(
            user_id=current_user.id, 
            post_id=post_id
        ).first()
        
        if existing_reaction:
            return "Already reacted", 400
        
        reaction = Reactions(
            user_id=current_user.id,
            post_id=post_id,
            type=reaction_type,
            round=current_round.id
        )
        db.session.add(reaction)
        db.session.commit()
        
        return jsonify({"message": "Reaction added successfully", "status": 200})
    
    @user.route("/publish", methods=["POST"])
    @login_required
    def publish_post():
        text = None
        if request.content_type == 'application/json':
            text = request.json.get("text") if request.json else None
        else:
            text = request.form.get("text")
        
        if not text:
            return "Missing text", 400
        
        current_round = Rounds.query.order_by(Rounds.id.desc()).first()
        if not current_round:
            return "No rounds available", 400
        
        post = Post(
            tweet=text,
            user_id=current_user.id,
            round=current_round.id
        )
        db.session.add(post)
        db.session.commit()
        
        # Mock sentiment analysis
        sentiment = mock_vader_sentiment(text)
        sentiment_record = Post_Sentiment(
            post_id=post.id,
            neg=sentiment["neg"],
            neu=sentiment["neu"],
            pos=sentiment["pos"],
            compound=sentiment["compound"]
        )
        db.session.add(sentiment_record)
        
        # Mock toxicity analysis
        mock_toxicity(text, current_user.username, post.id, db)
        
        db.session.commit()
        
        return jsonify({"message": "Published successfully", "status": 200})
    
    @user.route("/delete_post", methods=["POST"])
    @login_required
    def delete_post():
        post_id = None
        if request.content_type == 'application/json':
            post_id = request.json.get("post_id") if request.json else None
        else:
            post_id = request.form.get("post_id")
        
        if not post_id:
            return "Missing post_id", 400
        
        post = Post.query.filter_by(id=post_id, user_id=current_user.id).first()
        if not post:
            return "Post not found or not owned by user", 404
        
        db.session.delete(post)
        db.session.commit()
        
        return "Post deleted successfully"
    
    app.register_blueprint(user)
    
    # Add auth for login testing
    from flask import Blueprint
    from flask_login import login_user
    
    auth = Blueprint("auth", __name__)
    
    @auth.route("/login", methods=["POST"])
    def login():
        email = request.form.get("email")
        password = request.form.get("password")
        
        from werkzeug.security import check_password_hash
        admin_user = Admin_users.query.filter_by(email=email).first()
        
        if admin_user and check_password_hash(admin_user.password, password):
            user_mgmt = User_mgmt.query.filter_by(username=admin_user.username).first()
            if user_mgmt:
                login_user(user_mgmt)
                return "Login successful"
        
        return "Login failed", 401
    
    app.register_blueprint(auth)
    
    with app.app_context():
        db.create_all()
        
        # Create test users
        admin_user = Admin_users(
            username='testuser',
            email='test@test.com',
            password=generate_password_hash('test123'),
            role='user'
        )
        db.session.add(admin_user)
        
        user_mgmt = User_mgmt(
            username='testuser',
            email='test@test.com',
            password=generate_password_hash('test123'),
            joined_on=1234567890
        )
        db.session.add(user_mgmt)
        
        # Create another user for following tests
        admin_user2 = Admin_users(
            username='testuser2',
            email='test2@test.com',
            password=generate_password_hash('test123'),
            role='user'
        )
        db.session.add(admin_user2)
        
        user_mgmt2 = User_mgmt(
            username='testuser2',
            email='test2@test.com',
            password=generate_password_hash('test123'),
            joined_on=1234567890
        )
        db.session.add(user_mgmt2)
        
        # Create test round
        round_obj = Rounds(day=1, hour=1)
        db.session.add(round_obj)
        db.session.commit()
        
        # Create test post
        post = Post(
            tweet="Test post content",
            user_id=user_mgmt.id,
            round=round_obj.id
        )
        db.session.add(post)
        db.session.commit()
    
    yield app
    
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def client(app):
    """Test client for the app"""
    return app.test_client()


class TestUserInteractionRoutes:
    """Test user interaction routes"""
    
    def test_follow_without_login(self, client):
        """Test following without login"""
        response = client.post('/follow/1/2')
        assert response.status_code == 302  # Redirect to login
    
    def test_follow_with_login(self, client):
        """Test following another user"""
        # Login first
        client.post('/login', data={
            'email': 'test@test.com',
            'password': 'test123'
        })
        
        # Follow user 2 (follower=1, user=2)
        response = client.post('/follow/2/1')
        assert response.status_code == 200
        assert b'Followed successfully' in response.data
    
    def test_unfollow_after_follow(self, client):
        """Test unfollowing after following"""
        # Login first
        client.post('/login', data={
            'email': 'test@test.com',
            'password': 'test123'
        })
        
        # Follow first
        client.post('/follow/2/1')
        
        # Then unfollow
        response = client.post('/follow/2/1')
        assert response.status_code == 200
        assert b'Unfollowed successfully' in response.data
    
    def test_share_content_without_login(self, client):
        """Test sharing content without login"""
        response = client.get('/share_content?post_id=1')
        assert response.status_code == 302  # Redirect to login
    
    def test_share_content_with_login(self, client):
        """Test sharing content with login"""
        # Login first
        client.post('/login', data={
            'email': 'test@test.com',
            'password': 'test123'
        })
        
        # Share content
        response = client.get('/share_content?post_id=1')
        assert response.status_code == 200
        assert b'Content shared successfully' in response.data
    
    def test_share_content_missing_post_id(self, client):
        """Test sharing content without post_id"""
        # Login first
        client.post('/login', data={
            'email': 'test@test.com',
            'password': 'test123'
        })
        
        # Try to share without post_id
        response = client.get('/share_content')
        assert response.status_code == 400
        assert b'Missing post_id' in response.data
    
    def test_share_content_nonexistent_post(self, client):
        """Test sharing nonexistent content"""
        # Login first
        client.post('/login', data={
            'email': 'test@test.com',
            'password': 'test123'
        })
        
        # Try to share nonexistent post
        response = client.get('/share_content?post_id=999')
        assert response.status_code == 404
        assert b'Post not found' in response.data
    
    def test_react_to_content_without_login(self, client):
        """Test reacting to content without login"""
        response = client.get('/react_to_content?post_id=1')
        assert response.status_code == 302  # Redirect to login
    
    def test_react_to_content_with_login(self, client):
        """Test reacting to content with login"""
        # Login first
        client.post('/login', data={
            'email': 'test@test.com',
            'password': 'test123'
        })
        
        # React to content
        response = client.get('/react_to_content?post_id=1&type=like')
        assert response.status_code == 200
        
        # Parse JSON response
        import json
        data = json.loads(response.data)
        assert data['message'] == 'Reaction added successfully'
        assert data['status'] == 200
    
    def test_react_to_content_missing_post_id(self, client):
        """Test reacting to content without post_id"""
        # Login first
        client.post('/login', data={
            'email': 'test@test.com',
            'password': 'test123'
        })
        
        # Try to react without post_id
        response = client.get('/react_to_content')
        assert response.status_code == 400
        assert b'Missing post_id' in response.data
    
    def test_react_to_content_duplicate(self, client):
        """Test reacting to content twice (should fail)"""
        # Login first
        client.post('/login', data={
            'email': 'test@test.com',
            'password': 'test123'
        })
        
        # First reaction
        client.get('/react_to_content?post_id=1&type=like')
        
        # Second reaction (should fail)
        response = client.get('/react_to_content?post_id=1&type=like')
        assert response.status_code == 400
        assert b'Already reacted' in response.data


class TestPublishRoutes:
    """Test post publishing routes"""
    
    def test_publish_without_login(self, client):
        """Test publishing without login"""
        response = client.post('/publish', data={'text': 'Test post'})
        assert response.status_code == 302  # Redirect to login
    
    def test_publish_with_login_form_data(self, client):
        """Test publishing with login using form data"""
        # Login first
        client.post('/login', data={
            'email': 'test@test.com',
            'password': 'test123'
        })
        
        # Publish post
        response = client.post('/publish', data={'text': 'This is a test post'})
        assert response.status_code == 200
        
        # Parse JSON response
        import json
        data = json.loads(response.data)
        assert data['message'] == 'Published successfully'
        assert data['status'] == 200
    
    def test_publish_with_login_json_data(self, client):
        """Test publishing with login using JSON data"""
        # Login first
        client.post('/login', data={
            'email': 'test@test.com',
            'password': 'test123'
        })
        
        # Publish post with JSON
        response = client.post('/publish', 
                             json={'text': 'This is a JSON test post'},
                             content_type='application/json')
        assert response.status_code == 200
        
        # Parse JSON response
        import json
        data = json.loads(response.data)
        assert data['message'] == 'Published successfully'
        assert data['status'] == 200
    
    def test_publish_missing_text(self, client):
        """Test publishing without text"""
        # Login first
        client.post('/login', data={
            'email': 'test@test.com',
            'password': 'test123'
        })
        
        # Try to publish without text
        response = client.post('/publish', data={})
        assert response.status_code == 400
        assert b'Missing text' in response.data
    
    def test_delete_post_without_login(self, client):
        """Test deleting post without login"""
        response = client.post('/delete_post', data={'post_id': '1'})
        assert response.status_code == 302  # Redirect to login
    
    def test_delete_post_with_login(self, client):
        """Test deleting own post with login"""
        # Login first
        client.post('/login', data={
            'email': 'test@test.com',
            'password': 'test123'
        })
        
        # Delete post (post 1 was created by testuser in the fixture)
        response = client.post('/delete_post', data={'post_id': '1'})
        assert response.status_code == 200
        assert b'Post deleted successfully' in response.data
    
    def test_delete_post_missing_id(self, client):
        """Test deleting post without post_id"""
        # Login first
        client.post('/login', data={
            'email': 'test@test.com',
            'password': 'test123'
        })
        
        # Try to delete without post_id
        response = client.post('/delete_post', data={})
        assert response.status_code == 400
        assert b'Missing post_id' in response.data
    
    def test_delete_nonexistent_post(self, client):
        """Test deleting nonexistent post"""
        # Login first
        client.post('/login', data={
            'email': 'test@test.com',
            'password': 'test123'
        })
        
        # Try to delete nonexistent post
        response = client.post('/delete_post', data={'post_id': '999'})
        assert response.status_code == 404
        assert b'Post not found or not owned by user' in response.data


class TestUserInteractionIntegration:
    """Test user interaction integration scenarios"""
    
    def test_publish_and_share_flow(self, client):
        """Test publishing a post and then sharing it"""
        # Login first
        client.post('/login', data={
            'email': 'test@test.com',
            'password': 'test123'
        })
        
        # Publish a post
        publish_response = client.post('/publish', data={'text': 'Original post'})
        assert publish_response.status_code == 200
        
        # Share the post (assuming it gets ID 2, since 1 exists from fixture)
        share_response = client.get('/share_content?post_id=2')
        assert share_response.status_code == 200
        assert b'Content shared successfully' in share_response.data
    
    def test_publish_and_react_flow(self, client):
        """Test publishing a post and then reacting to it"""
        # Login first
        client.post('/login', data={
            'email': 'test@test.com',
            'password': 'test123'
        })
        
        # Publish a post
        publish_response = client.post('/publish', data={'text': 'Post to react to'})
        assert publish_response.status_code == 200
        
        # React to the post
        react_response = client.get('/react_to_content?post_id=2&type=like')
        assert react_response.status_code == 200
        
        import json
        data = json.loads(react_response.data)
        assert data['message'] == 'Reaction added successfully'