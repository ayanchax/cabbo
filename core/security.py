from fastapi import Depends, Header
from core.exceptions import CabboException
from core.config import settings
import jwt
from models.customer.customer_orm import Customer
from db.database import get_mysql_session
from sqlalchemy.orm import Session

def cabbo_auth(
    authorization: str = Header(..., description="Bearer token for authentication"),
    db: Session = Depends(get_mysql_session)
) -> Customer:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise CabboException("Authorization header missing or invalid.", status_code=401)
    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_jwt_token(token)
        customer_id = payload.get("sub")
        if not customer_id:
            raise CabboException("Invalid token: missing subject.", status_code=401)
        customer = db.query(Customer).filter(Customer.id == customer_id, Customer.bearer_token == token, Customer.is_active == True).first()
        if not customer:
            raise CabboException("Invalid or expired token.", status_code=401)
        return customer
    except jwt.ExpiredSignatureError:
        raise CabboException("Token has expired.", status_code=401)
    except jwt.InvalidTokenError:
        raise CabboException("Invalid token.", status_code=401)

def generate_jwt_token(payload, secret=settings.JWT_SECRET,algorithm="HS256"):
    """
    Generate a JWT token with a secret key.
    """
    
    return jwt.encode(payload, secret, algorithm=algorithm)

def decode_jwt_token(token, secret=settings.JWT_SECRET, algorithms=["HS256"]):
    """
    Decode a JWT token with a secret key.
    """
    
    return jwt.decode(token, secret, algorithms=algorithms)

 
 