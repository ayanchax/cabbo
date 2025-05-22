from core.config import settings
import jwt
def generate_jwt_token(payload, secret=settings.JWT_SECRET,algorithm="HS256"):
    """
    Generate a JWT token with a secret key.
    """
    
    return jwt.encode(payload, secret, algorithm=algorithm)