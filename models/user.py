from flask import current_app
from auth0.v3.management import Auth0
from flask_login import UserMixin
from your_app import db  # or wherever your db instance is defined


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    auth0_id = db.Column(db.String(100), unique=True, nullable=False)
    # ... other fields ...

    def get_roles(self):
        """
        Retrieves the user's roles from Auth0 using the Management API.
        Ensure that `AUTH0_DOMAIN` and `AUTH0_MGMT_API_TOKEN` are set in your app configuration.
        """
        domain = current_app.config.get("AUTH0_DOMAIN")
        mgmt_api_token = current_app.config.get("AUTH0_MGMT_API_TOKEN")
        if not domain or not mgmt_api_token:
            raise Exception(
                "Missing Auth0 configuration. Set AUTH0_DOMAIN and AUTH0_MGMT_API_TOKEN in your environment."
            )

        # Instantiate Auth0 Management client
        auth0_client = Auth0(domain, mgmt_api_token)
        # Retrieve roles for this user
        user_roles = auth0_client.users.get_user_roles(self.auth0_id)
        return user_roles

    @property
    def roles(self):
        """
        Property to access user roles. This can be used in templates or business logic.
        """
        return self.get_roles()
