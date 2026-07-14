# -*- coding: utf-8 -*-
"""PostgreSQL 커넥션 관리.

로드맵: S1.1, B.1 저장소
Neo4j 커넥션은 Stage 2(ontology)에서 추가. 지금은 PostgreSQL 만.
"""
from __future__ import annotations

import os

import psycopg

from .config import load_env


def connect() -> psycopg.Connection:
    """.env 를 로드해 PostgreSQL 에 연결."""
    load_env()
    return psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        dbname=os.environ.get("POSTGRES_DB", "gxpai"),
        user=os.environ.get("POSTGRES_USER", "gxpai"),
        password=os.environ.get("POSTGRES_PASSWORD", "gxpai_dev"),
    )


def neo4j_driver():
    """.env 를 로드해 Neo4j 드라이버 반환 (Stage 2 온톨로지)."""
    from neo4j import GraphDatabase
    load_env()
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    pw = os.environ.get("NEO4J_PASSWORD", "gxpai_dev_pw")
    return GraphDatabase.driver(uri, auth=(user, pw))
