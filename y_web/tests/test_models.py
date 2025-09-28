"""
Tests for y_web database models
"""
import pytest
from y_web import db
from y_web.models import (
    User_mgmt, Post, Admin_users, Hashtags, Emotions, Post_emotions,
    Post_hashtags, Mentions, Reactions, Follow, Rounds, Articles, Websites
)
from werkzeug.security import generate_password_hash, check_password_hash


class TestUserMgmt:
    """Test User_mgmt model"""
    
    def test_user_creation(self, app):
        """Test creating a user"""
        with app.app_context():
            user = User_mgmt(
                username='testuser2',
                email='test2@example.com',
                password=generate_password_hash('password123'),
                joined_on=1234567890
            )
            db.session.add(user)
            db.session.commit()
            
            assert user.id is not None
            assert user.username == 'testuser2'
            assert user.email == 'test2@example.com'
            assert user.joined_on == 1234567890
            assert user.leaning == 'neutral'  # default value
            assert user.user_type == 'user'  # default value
    
    def test_user_defaults(self, app):
        """Test user model default values"""
        with app.app_context():
            user = User_mgmt(
                username='defaultuser',
                password=generate_password_hash('password'),
                joined_on=1234567890
            )
            db.session.add(user)
            db.session.commit()
            
            assert user.leaning == 'neutral'
            assert user.user_type == 'user'
            assert user.age == 0
            assert user.recsys_type == 'default'
            assert user.frecsys_type == 'default'
            assert user.language == 'en'
            assert user.toxicity == 'no'
            assert user.is_page == 0
            assert user.daily_activity_level == 1
    
    def test_user_relationships(self, app):
        """Test user model relationships"""
        with app.app_context():
            user = User_mgmt(
                username='reluser',
                password=generate_password_hash('password'),
                joined_on=1234567890
            )
            db.session.add(user)
            db.session.commit()
            
            # Test posts relationship
            assert hasattr(user, 'posts')
            assert hasattr(user, 'liked')


class TestPost:
    """Test Post model"""
    
    def test_post_creation(self, app):
        """Test creating a post"""
        with app.app_context():
            user = User_mgmt(
                username='postuser',
                password=generate_password_hash('password'),
                joined_on=1234567890
            )
            db.session.add(user)
            db.session.commit()
            
            post = Post(
                tweet='This is a test post',
                round=1,
                user_id=user.id
            )
            db.session.add(post)
            db.session.commit()
            
            assert post.id is not None
            assert post.tweet == 'This is a test post'
            assert post.round == 1
            assert post.user_id == user.id
            assert post.comment_to == -1  # default value
            assert post.shared_from == -1  # default value
            assert post.reaction_count == 0  # default value


class TestAdminUsers:
    """Test Admin_users model"""
    
    def test_admin_user_creation(self, app):
        """Test creating an admin user"""
        with app.app_context():
            admin = Admin_users(
                username='admin2',
                email='admin2@test.com',
                password=generate_password_hash('admin123'),
                role='admin'
            )
            db.session.add(admin)
            db.session.commit()
            
            assert admin.id is not None
            assert admin.username == 'admin2'
            assert admin.email == 'admin2@test.com'
            assert admin.role == 'admin'
            assert check_password_hash(admin.password, 'admin123')


class TestHashtags:
    """Test Hashtags model"""
    
    def test_hashtag_creation(self, app):
        """Test creating a hashtag"""
        with app.app_context():
            hashtag = Hashtags(hashtag='#test')
            db.session.add(hashtag)
            db.session.commit()
            
            assert hashtag.id is not None
            assert hashtag.hashtag == '#test'


class TestEmotions:
    """Test Emotions model"""
    
    def test_emotion_creation(self, app):
        """Test creating an emotion"""
        with app.app_context():
            emotion = Emotions(emotion='happy', icon='😊')
            db.session.add(emotion)
            db.session.commit()
            
            assert emotion.id is not None
            assert emotion.emotion == 'happy'
            assert emotion.icon == '😊'


class TestReactions:
    """Test Reactions model"""
    
    def test_reaction_creation(self, app):
        """Test creating a reaction"""
        with app.app_context():
            user = User_mgmt(
                username='reactuser',
                password=generate_password_hash('password'),
                joined_on=1234567890
            )
            db.session.add(user)
            
            post = Post(
                tweet='Test post for reaction',
                round=1,
                user_id=user.id
            )
            db.session.add(post)
            db.session.commit()
            
            reaction = Reactions(
                round=1,
                user_id=user.id,
                post_id=post.id,
                type='like'
            )
            db.session.add(reaction)
            db.session.commit()
            
            assert reaction.id is not None
            assert reaction.round == 1
            assert reaction.user_id == user.id
            assert reaction.post_id == post.id
            assert reaction.type == 'like'


class TestFollow:
    """Test Follow model"""
    
    def test_follow_creation(self, app):
        """Test creating a follow relationship"""
        with app.app_context():
            user1 = User_mgmt(
                username='follower',
                password=generate_password_hash('password'),
                joined_on=1234567890
            )
            user2 = User_mgmt(
                username='followee',
                password=generate_password_hash('password'),
                joined_on=1234567890
            )
            db.session.add(user1)
            db.session.add(user2)
            db.session.commit()
            
            follow = Follow(
                user_id=user2.id,
                follower_id=user1.id,
                round=1,
                action='follow'
            )
            db.session.add(follow)
            db.session.commit()
            
            assert follow.id is not None
            assert follow.user_id == user2.id
            assert follow.follower_id == user1.id
            assert follow.round == 1
            assert follow.action == 'follow'


class TestRounds:
    """Test Rounds model"""
    
    def test_round_creation(self, app):
        """Test creating a round"""
        with app.app_context():
            round_obj = Rounds(day=1, hour=12)
            db.session.add(round_obj)
            db.session.commit()
            
            assert round_obj.id is not None
            assert round_obj.day == 1
            assert round_obj.hour == 12


class TestWebsites:
    """Test Websites model"""
    
    def test_website_creation(self, app):
        """Test creating a website"""
        with app.app_context():
            website = Websites(
                name='Test News',
                rss='https://testnews.com/rss',
                leaning='neutral',
                category='news',
                last_fetched=1234567890,
                language='en',
                country='us'
            )
            db.session.add(website)
            db.session.commit()
            
            assert website.id is not None
            assert website.name == 'Test News'
            assert website.rss == 'https://testnews.com/rss'
            assert website.leaning == 'neutral'
            assert website.category == 'news'


class TestArticles:
    """Test Articles model"""
    
    def test_article_creation(self, app):
        """Test creating an article"""
        with app.app_context():
            website = Websites(
                name='Test News',
                rss='https://testnews.com/rss',
                leaning='neutral',
                category='news',
                last_fetched=1234567890,
                language='en',
                country='us'
            )
            db.session.add(website)
            db.session.commit()
            
            article = Articles(
                title='Test Article',
                summary='This is a test article summary',
                website_id=website.id,
                link='https://testnews.com/article/1',
                fetched_on=1234567890
            )
            db.session.add(article)
            db.session.commit()
            
            assert article.id is not None
            assert article.title == 'Test Article'
            assert article.summary == 'This is a test article summary'
            assert article.website_id == website.id
            assert article.link == 'https://testnews.com/article/1'