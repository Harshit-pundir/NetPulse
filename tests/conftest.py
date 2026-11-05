import re
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from werkzeug.security import generate_password_hash
from app.database import Base, get_db
from app.main import app
from app.models import User


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    app.state.test_session_factory = testing_session
    Base.metadata.create_all(engine)
    with testing_session() as session:
        session.add_all([User(username="admin", password_hash=generate_password_hash("pass"), role="ADMIN"), User(username="viewer", password_hash=generate_password_hash("pass"), role="VIEWER")]); session.commit()
    def test_db():
        session = testing_session()
        try: yield session
        finally: session.close()
    app.dependency_overrides[get_db] = test_db
    with TestClient(app) as test_client: yield test_client
    app.dependency_overrides.clear(); Base.metadata.drop_all(engine); engine.dispose()


def csrf_token(client, path="/login"):
    html = client.get(path, follow_redirects=True).text
    return re.search(r'name="csrf-token" content="([^"]+)', html).group(1)


def login(client, username="admin"):
    token = csrf_token(client)
    return client.post("/login", data={"username": username, "password": "pass", "csrf_token": token}, follow_redirects=True)


def csrf_headers(client):
    return {"X-CSRF-Token": csrf_token(client, "/")}
