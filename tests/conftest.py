import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import User


@pytest.fixture
def app():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SECRET_KEY": "test",
    })
    with app.app_context():
        db.create_all()
        db.session.add(User(username="admin", password_hash=generate_password_hash("pass"), role="ADMIN"))
        db.session.add(User(username="viewer", password_hash=generate_password_hash("pass"), role="VIEWER"))
        db.session.commit()
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, username="admin"):
    client.get("/login")
    token = csrf_token(client)
    return client.post("/login", data={"username": username, "password": "pass", "csrf_token": token}, follow_redirects=True)


def csrf_token(client):
    with client.session_transaction() as session:
        return session.get("csrf_token", "")


def csrf_headers(client):
    return {"X-CSRF-Token": csrf_token(client)}


@pytest.fixture
def admin(client):
    login(client)
    return client


@pytest.fixture
def viewer(client):
    login(client, "viewer")
    return client
