from app import app, db, Admin
from werkzeug.security import generate_password_hash
from getpass import getpass


with app.app_context():

    username = input("Enter admin username: ").strip()
    password = getpass("Enter admin password: ")

    existing_admin = Admin.query.filter_by(
        username=username
    ).first()

    if existing_admin:
        print("An admin with this username already exists.")

    else:
        password_hash = generate_password_hash(password)

        admin = Admin(
            username=username,
            password_hash=password_hash
        )

        db.session.add(admin)
        db.session.commit()

        print("Admin account created successfully.")