"""Persistencia de cuentas, sesiones y catálogo compartido."""

from sqlmodel import Field, SQLModel


class Account(SQLModel, table=True):
    __tablename__ = "accounts"
    username: str = Field(primary_key=True)
    role: str
    password_hash: str | None = None


class AccountSession(SQLModel, table=True):
    __tablename__ = "account_sessions"
    digest: str = Field(primary_key=True)
    username: str = Field(foreign_key="accounts.username")
    expires_at: float = Field(index=True)
    viewing_role: str | None = None


class CatalogueGroup(SQLModel, table=True):
    __tablename__ = "catalogue_groups"
    id: str = Field(primary_key=True)
    kind: str
    name: str


class PublishedDesign(SQLModel, table=True):
    __tablename__ = "published_designs"
    id: str = Field(primary_key=True)
    name: str
    family: str
    project: str
    filename: str
    media_type: str
    sha256: str
    size: int
    published_at: float
    published_by: str = Field(foreign_key="accounts.username")
