import os
import json
import re
from decimal import Decimal
from datetime import datetime

import psycopg2
import ollama
from dotenv import load_dotenv
from groq import Groq


# =========================================================
# CONFIGURATION
# =========================================================

# cd .\NaturalLanguageSQLAgent
# uvicorn app:app --reload
# http://127.0.0.1:8000/ui

# -------------------------
# Groq
# -------------------------

GROQ_MODEL = "qwen/qwen3.8-27b"

# Maximum output tokens for SQL generation.
# We do not need a huge answer because the model only creates SQL JSON.
GROQ_MAX_TOKENS = 1200


# -------------------------
# Ollama fallback
# -------------------------

OLLAMA_MODEL = "qwen2.5:7b"


# -------------------------
# Database
# -------------------------

DB_HOST = "localhost"
DB_NAME = "business_intelligence"
DB_USER = "postgres"
DB_PORT = "5432"

QUERY_TIMEOUT_MS = 10000

# Maximum rows returned to the application
MAX_ROWS = 1000

# One automatic SQL correction attempt
MAX_SQL_RETRIES = 1


# =========================================================
# ENVIRONMENT
# =========================================================

load_dotenv()

db_password = os.getenv("DB_PASSWORD")
groq_api_key = os.getenv("GROQ_API_KEY")


if not db_password:
    raise RuntimeError(
        "Database configuration is missing."
    )


# =========================================================
# GROQ CLIENT
# =========================================================

groq_client = None

if groq_api_key:
    try:
        groq_client = Groq(
            api_key=groq_api_key
        )
    except Exception:
        groq_client = None


# =========================================================
# DATABASE CONNECTION
# =========================================================

def create_connection():

    try:

        return psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=db_password,
            port=DB_PORT
        )

    except psycopg2.Error:

        raise RuntimeError(
            "Unable to connect to the business database."
        )


connection = create_connection()
cursor = connection.cursor()


# =========================================================
# LOAD COMPLETE DATABASE SCHEMA
# =========================================================

def load_schema():

    try:

        # -------------------------------------------------
        # Tables + columns
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT
                table_name,
                column_name,
                data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position
            """
        )

        column_rows = cursor.fetchall()


        # -------------------------------------------------
        # Primary keys
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT
                tc.table_name,
                kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            WHERE tc.table_schema = 'public'
              AND tc.constraint_type = 'PRIMARY KEY'
            ORDER BY
                tc.table_name,
                kcu.ordinal_position
            """
        )

        primary_key_rows = cursor.fetchall()


        # -------------------------------------------------
        # Foreign keys
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT
                tc.table_name,
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
                ON ccu.constraint_name = tc.constraint_name
                AND ccu.table_schema = tc.table_schema
            WHERE tc.table_schema = 'public'
              AND tc.constraint_type = 'FOREIGN KEY'
            ORDER BY
                tc.table_name,
                kcu.column_name
            """
        )

        foreign_key_rows = cursor.fetchall()


        # -------------------------------------------------
        # Primary key map
        # -------------------------------------------------

        primary_keys = {}

        for table, column in primary_key_rows:

            primary_keys.setdefault(
                table,
                []
            ).append(column)


        # -------------------------------------------------
        # Build schema
        # -------------------------------------------------

        schema_parts = []

        current_table = None

        for table, column, data_type in column_rows:

            if table != current_table:

                schema_parts.append(
                    f"\nTable: {table}"
                )

                current_table = table

            key_info = ""

            if column in primary_keys.get(
                table,
                []
            ):

                key_info += " [PRIMARY KEY]"

            schema_parts.append(
                f"  - {column} "
                f"({data_type})"
                f"{key_info}"
            )


        # -------------------------------------------------
        # Relationships
        # -------------------------------------------------

        if foreign_key_rows:

            schema_parts.append(
                "\nRELATIONSHIPS:"
            )

            for (
                table,
                column,
                foreign_table,
                foreign_column
            ) in foreign_key_rows:

                schema_parts.append(
                    f"  - {table}.{column} "
                    f"-> "
                    f"{foreign_table}.{foreign_column}"
                )


        return "\n".join(schema_parts)

    except psycopg2.Error:

        connection.rollback()

        raise RuntimeError(
            "Unable to read database structure."
        )


schema = load_schema()


# =========================================================
# CHECK OLLAMA
# =========================================================

def ollama_available():

    try:

        ollama.list()

        return True

    except Exception:

        return False


# =========================================================
# SQL NORMALIZATION
# =========================================================

def normalize_sql(sql):

    if not sql:
        return ""

    sql = sql.strip()

    # Remove accidental markdown fences
    sql = re.sub(
        r"^```(?:sql)?\s*",
        "",
        sql,
        flags=re.IGNORECASE
    )

    sql = re.sub(
        r"\s*```$",
        "",
        sql,
        flags=re.IGNORECASE
    )

    sql = sql.strip()

    # Remove one harmless final semicolon
    sql = sql.rstrip(";").strip()

    return sql


# =========================================================
# SQL SAFETY
# =========================================================

def is_safe_sql(sql):

    sql = normalize_sql(sql)

    if not sql:
        return False

    # Only SELECT / WITH
    if not re.match(
        r"^(SELECT|WITH)\b",
        sql,
        re.IGNORECASE
    ):
        return False

    # No multiple statements
    if ";" in sql:
        return False

    # No SQL comments
    if "--" in sql:
        return False

    if "/*" in sql or "*/" in sql:
        return False

    dangerous_keywords = [
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "ALTER",
        "TRUNCATE",
        "CREATE",
        "GRANT",
        "REVOKE",
        "MERGE",
        "CALL",
        "EXECUTE",
        "COPY",
        "VACUUM",
        "REFRESH"
    ]

    for keyword in dangerous_keywords:

        if re.search(
            rf"\b{keyword}\b",
            sql,
            re.IGNORECASE
        ):
            return False

    return True


# =========================================================
# CLEAN MODEL JSON
# =========================================================

def clean_json(output):

    if not output:
        return None

    output = output.strip()

    # Remove markdown fences
    output = re.sub(
        r"```json\s*",
        "",
        output,
        flags=re.IGNORECASE
    )

    output = re.sub(
        r"```sql\s*",
        "",
        output,
        flags=re.IGNORECASE
    )

    output = output.replace(
        "```",
        ""
    ).strip()

    # Locate JSON object
    start = output.find("{")
    end = output.rfind("}")

    if start == -1 or end == -1:
        return None

    try:

        data = json.loads(
            output[start:end + 1]
        )

    except json.JSONDecodeError:

        return None

    if not isinstance(data, dict):
        return None

    sql = data.get("sql")

    if not isinstance(sql, str):
        return None

    task = data.get(
        "task",
        "Business result"
    )

    if not isinstance(task, str):
        task = "Business result"

    sql = normalize_sql(sql)

    if not is_safe_sql(sql):
        return None

    return {
        "task": task.strip() or "Business result",
        "sql": sql
    }


# =========================================================
# BUILD SQL PROMPT
# =========================================================

def build_sql_prompt(question):

    current_date = datetime.now().strftime(
        "%Y-%m-%d"
    )

    prompt = f"""
You are a production-grade Natural Language
Business Intelligence SQL engine.

Your task is to understand the user's COMPLETE
business question and generate ONE correct PostgreSQL
read-only query using the CURRENT database schema.

The database is dynamic.

Records can be added, removed or modified after deployment.

Never hard-code a database answer.

DATABASE SCHEMA:
{schema}

CURRENT DATE:
{current_date}

USER QUESTION:
{question}

RETURN ONLY VALID JSON:

{{
    "task": "short description of the complete request",
    "sql": "one PostgreSQL SELECT or WITH query"
}}

IMPORTANT RULES:

1. Use ONLY tables present in the schema.

2. Use ONLY columns present in the schema.

3. Determine joins from actual PRIMARY KEY and
   FOREIGN KEY relationships.

4. Never invent tables.

5. Never invent columns.

6. Never invent database values.

7. Never hard-code database results.

8. Always calculate results from the current database.

9. The database contents may change after deployment.

10. Do not create special handling for any particular
    question.

11. Do not create special handling for any particular
    product, category, customer, city or value.

12. Do not assume a database value exists unless it is
    supplied by the user or discovered by SQL.

READ-ONLY SQL:

Generate exactly ONE SQL statement.

It must begin with:

SELECT

or:

WITH ... SELECT

Never generate:

INSERT
UPDATE
DELETE
DROP
ALTER
TRUNCATE
CREATE
GRANT
REVOKE
MERGE
CALL
EXECUTE
COPY
VACUUM
REFRESH

Do not generate comments.
Do not generate multiple SQL statements.

COMPLETE QUESTION:

The user may ask multiple requirements in one question.

Understand ALL requirements.

The SQL should answer all requirements that can
reasonably be answered by one SQL query.

Possible operations:

- listing
- filtering
- sorting
- counting
- SUM
- AVG
- MIN
- MAX
- grouping
- ranking
- comparison
- percentage
- date analysis
- combinations of these

Do not solve only one part of a multi-part question.

LIST + COMPARISON:

If the user asks for a list AND asks which record
has the highest or lowest value:

Do NOT return only the highest/lowest record.

Keep every row required for the requested list.

Use appropriate SQL techniques such as:

- window functions
- CTEs
- ranking
- conditional expressions
- aggregation

For example:

MAX(value) OVER ()

can calculate the maximum while retaining all
requested rows.

The result must contain enough information to identify:

1. all requested records
2. the value being compared
3. which record owns the highest/lowest value

Do not use LIMIT 1 merely because a highest/lowest
comparison exists.

ONLY HIGHEST / LOWEST:

If the user asks ONLY for the highest, lowest,
maximum or minimum record:

return the appropriate result.

TOP / BOTTOM:

If the user explicitly asks for TOP N or BOTTOM N:

use the N provided by the user.

Do not invent N.

If no limit is requested, do not add an arbitrary
LIMIT merely to make the query easier.

FILTERS:

If the user provides a filter:

1. Identify the appropriate column from the schema.
2. Use the user's supplied value.
3. Do not replace it with an invented value.

If the user does not provide a filter:
do not invent one.

GROUPING:

When the user asks for results by a database dimension
such as product, category, customer, region or date:

identify the appropriate schema column.

Use GROUP BY when aggregation is required.

AGGREGATION:

Use the correct PostgreSQL aggregate:

SUM
COUNT
AVG
MIN
MAX

Choose the appropriate column based on the actual
schema and meaning of the question.

REVENUE:

If order_items.line_total exists and represents
the final line amount:

Revenue = SUM(order_items.line_total)

For product-level revenue, use the actual relationship
between the relevant tables.

Do NOT calculate revenue as:

unit_price * quantity

when line_total already represents the final line amount.

PERCENTAGE:

If the user asks for percentage contribution:

calculate it dynamically from the current database.

Never hard-code totals.

Use appropriate SQL aggregation and/or window functions.

DATE QUESTIONS:

Use actual date/timestamp columns from the schema.

For relative date questions:

- use PostgreSQL date functions
- use CURRENT_DATE where appropriate
- calculate dates dynamically
- never hard-code today's date
- never hard-code a month or year

LIMIT:

Do not add LIMIT unless:

1. the user explicitly requests a limited number
   of records,

OR

2. limiting is genuinely required for the requested
   ranking/result.

Never use LIMIT 1 simply because the question contains
a highest/lowest comparison.

FINAL QUALITY CHECK:

Before returning JSON verify:

1. Every table exists.
2. Every column exists.
3. Joins use actual relationships.
4. Filters come from the user question.
5. No database value is invented.
6. Calculations are dynamic.
7. Every part of the question is addressed.
8. Requested rows are retained.
9. Ranking logic is correct.
10. Percentage calculations are correct.
11. Revenue uses the correct field.
12. Relative dates are dynamic.
13. Query is read-only.
14. There is exactly ONE SQL statement.
15. SQL is valid PostgreSQL.

RETURN ONLY JSON.
"""

    return prompt


# =========================================================
# GROQ SQL GENERATION
# =========================================================

def generate_sql_groq(question):

    if not groq_client:
        return None

    prompt = build_sql_prompt(question)

    try:

        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You generate safe, correct PostgreSQL "
                        "queries for a business intelligence system. "
                        "Return only valid JSON."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0,
            max_tokens=GROQ_MAX_TOKENS,
            response_format={
                "type": "json_object"
            }
        )

        output = (
            response
            .choices[0]
            .message
            .content
        )

        return clean_json(output)

    except Exception:

        return None


# =========================================================
# OLLAMA SQL GENERATION
# =========================================================

def generate_sql_ollama(question):

    prompt = build_sql_prompt(question)

    try:

        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            options={
                "temperature": 0
            }
        )

        output = (
            response["message"]["content"]
            .strip()
        )

        return clean_json(output)

    except Exception:

        return None


# =========================================================
# READ-ONLY REQUEST GUARD
# =========================================================

def is_write_request(question):
    """
    Detect database modification requests BEFORE calling an LLM.
    This prevents DELETE/UPDATE/INSERT/etc. from reaching SQL
    generation and saves an unnecessary API call.
    """

    if not question:
        return False

    q = " ".join(question.strip().lower().split())

    write_patterns = [
        r"\bdelete\b\s+(the|all|any|some|this|these|those|my|our)?",
        r"\bremove\b\s+(the|all|any|some|this|these|those|my|our)?",
        r"\berase\b\s+(the|all|any|some|this|these|those|my|our)?",
        r"\btruncate\b",
        r"\bdrop\b\s+(table|database|schema|column|index|view)",
        r"\bupdate\b\s+(the|a|an|this|these|those|my|our)?",
        r"\bmodify\b\s+(the|a|an|this|these|those|my|our)?",
        r"\bchange\b\s+(the|a|an|this|these|those|my|our)?",
        r"\binsert\b\s+(the|a|an|new|some|this|these|those)?",
        r"\badd\b\s+(a|an|new|another)\s+",
        r"\bcreate\b\s+(a|an|new)\s+(table|database|schema|view|index)",
    ]

    return any(
        re.search(pattern, q, re.IGNORECASE)
        for pattern in write_patterns
    )


def read_only_rejection_plan():
    """
    Return a harmless SELECT so the existing UI can display the
    rejection without requiring changes to app.py.
    """

    message = (
        "This assistant is read-only and cannot modify or delete "
        "database data. You can ask me to view, analyze, compare, "
        "or summarize your data."
    )

    safe_message = message.replace("'", "''")

    return {
        "task": "Read-only restriction",
        "sql": f"SELECT '{safe_message}' AS message"
    }


# =========================================================
# GENERATE SQL WITH GROQ + OLLAMA — NO CACHE
# =========================================================

def generate_sql(question):

    # -----------------------------------------------------
    # 1. BLOCK WRITE REQUESTS BEFORE LLM CALL
    # -----------------------------------------------------

    if is_write_request(question):
        return read_only_rejection_plan()


    # -----------------------------------------------------
    # 2. GROQ
    # -----------------------------------------------------

    groq_plan = generate_sql_groq(
        question
    )

    if groq_plan:
        return groq_plan


    # -----------------------------------------------------
    # 3. OLLAMA FALLBACK
    # -----------------------------------------------------

    ollama_plan = generate_sql_ollama(
        question
    )

    if ollama_plan:
        return ollama_plan


    return None


# =========================================================
# EXECUTE SQL
# =========================================================

def execute_query(sql):

    sql = normalize_sql(sql)

    if not is_safe_sql(sql):

        return (
            None,
            None,
            False,
            "Generated SQL failed safety validation."
        )

    try:

        # -------------------------------------------------
        # Read-only transaction
        # -------------------------------------------------

        cursor.execute(
            "SET TRANSACTION READ ONLY"
        )

        cursor.execute(
            f"SET LOCAL statement_timeout = "
            f"{QUERY_TIMEOUT_MS}"
        )

        # -------------------------------------------------
        # Execute query
        # -------------------------------------------------

        cursor.execute(sql)

        if cursor.description is None:

            connection.rollback()

            return (
                None,
                None,
                False,
                "Query did not return data."
            )

        columns = [
            description[0]
            for description in cursor.description
        ]

        results = cursor.fetchmany(
            MAX_ROWS
        )

        connection.rollback()

        return (
            results,
            columns,
            True,
            None
        )

    except psycopg2.Error as e:

        error_message = str(e)

        connection.rollback()

        return (
            None,
            None,
            False,
            error_message
        )


# =========================================================
# BUILD REPAIR PROMPT
# =========================================================

def build_repair_prompt(
    question,
    failed_sql,
    database_error
):

    prompt = f"""
You are a production-grade PostgreSQL SQL correction engine.

A dynamically generated SQL query failed during execution.

Correct ONLY the SQL so that it answers the ORIGINAL
user question correctly.

Do not change the meaning of the question.

DATABASE SCHEMA:

{schema}

USER QUESTION:

{question}

FAILED SQL:

{failed_sql}

DATABASE ERROR:

{database_error}

CORRECTION RULES:

1. Return exactly ONE PostgreSQL SELECT or WITH query.

2. Use only tables and columns from the schema.

3. Use actual PRIMARY KEY and FOREIGN KEY relationships.

4. Do not invent database values.

5. Do not hard-code answers.

6. Preserve EVERY requirement of the original question.

7. Fix the actual SQL problem indicated by the error.

8. Keep calculations dynamic.

9. Do not add special handling for a particular question.

10. Do not add special handling for a particular product,
category, customer or value.

11. If the original question asks for a list plus
highest/lowest comparison, retain the complete list.

12. If the question asks for percentages, calculate
them dynamically.

13. If revenue is requested and line_total exists,
use the appropriate SUM(line_total).

14. Do not use unit_price * quantity for revenue when
line_total represents the final line amount.

15. Do not hard-code dates.

16. Do not generate comments.

17. Do not generate multiple SQL statements.

18. The query must be read-only.

Never generate:

INSERT
UPDATE
DELETE
DROP
ALTER
TRUNCATE
CREATE
GRANT
REVOKE
MERGE
CALL
EXECUTE
COPY
VACUUM
REFRESH

RETURN ONLY VALID JSON:

{{
    "task": "short description",
    "sql": "corrected PostgreSQL SELECT or WITH query"
}}
"""

    return prompt


# =========================================================
# GROQ SQL REPAIR
# =========================================================

def repair_sql_groq(
    question,
    failed_sql,
    database_error
):

    if not groq_client:
        return None

    prompt = build_repair_prompt(
        question,
        failed_sql,
        database_error
    )

    try:

        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You correct PostgreSQL queries. "
                        "Return only valid JSON."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0,
            max_tokens=GROQ_MAX_TOKENS,
            response_format={
                "type": "json_object"
            }
        )

        output = (
            response
            .choices[0]
            .message
            .content
        )

        return clean_json(output)

    except Exception:

        return None


# =========================================================
# OLLAMA SQL REPAIR
# =========================================================

def repair_sql_ollama(
    question,
    failed_sql,
    database_error
):

    prompt = build_repair_prompt(
        question,
        failed_sql,
        database_error
    )

    try:

        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            options={
                "temperature": 0
            }
        )

        output = (
            response["message"]["content"]
            .strip()
        )

        return clean_json(output)

    except Exception:

        return None


# =========================================================
# SQL REPAIR WITH GROQ + OLLAMA FALLBACK
# =========================================================

def repair_sql(
    question,
    failed_sql,
    database_error
):

    # First try Groq
    repaired_plan = repair_sql_groq(
        question,
        failed_sql,
        database_error
    )

    if repaired_plan:

        return repaired_plan


    # If Groq fails, use Ollama
    repaired_plan = repair_sql_ollama(
        question,
        failed_sql,
        database_error
    )

    return repaired_plan


# =========================================================
# RUN QUERY WITH AUTOMATIC REPAIR
# =========================================================

def run_query_with_repair(
    question,
    plan
):

    if not plan:

        return (
            None,
            None,
            False,
            None
        )

    task = plan.get(
        "task",
        "Business result"
    )

    sql = plan.get(
        "sql",
        ""
    )

    # -----------------------------------------------------
    # First execution
    # -----------------------------------------------------

    results, columns, success, error = (
        execute_query(sql)
    )

    if success:

        return (
            task,
            sql,
            results,
            columns
        )

    # -----------------------------------------------------
    # One repair attempt
    # -----------------------------------------------------

    for _ in range(MAX_SQL_RETRIES):

        repaired_plan = repair_sql(
            question,
            sql,
            error
        )

        if not repaired_plan:

            return (
                None,
                None,
                False,
                None
            )

        repaired_sql = repaired_plan.get(
            "sql",
            ""
        )

        repaired_task = repaired_plan.get(
            "task",
            task
        )

        results, columns, success, error = (
            execute_query(
                repaired_sql
            )
        )

        if success:

            return (
                repaired_task,
                repaired_sql,
                results,
                columns
            )

        return (
            None,
            None,
            False,
            None
        )

    return (
        None,
        None,
        False,
        None
    )


# =========================================================
# VALUE FORMATTING
# =========================================================

def format_value(value):

    if value is None:

        return "N/A"

    if isinstance(value, Decimal):

        if value == value.to_integral_value():

            return f"{int(value):,}"

        return f"{value:,.2f}"

    if isinstance(value, float):

        return f"{value:,.2f}"

    if isinstance(value, int):

        return f"{value:,}"

    return str(value)


# =========================================================
# RESULT FORMATTING
# =========================================================

def format_result(
    task,
    columns,
    results
):

    if not results:

        return (
            f"{task}: "
            "No matching data was found."
        )

    # -----------------------------------------------------
    # Single value
    # -----------------------------------------------------

    if (
        len(columns) == 1
        and len(results) == 1
    ):

        return (
            f"{task.title()}: "
            f"{format_value(results[0][0])}"
        )

    # -----------------------------------------------------
    # Multiple rows
    # -----------------------------------------------------

    lines = []

    for row in results:

        parts = []

        for column, value in zip(
            columns,
            row
        ):

            display_name = (
                column
                .replace("_", " ")
                .title()
            )

            parts.append(
                f"{display_name}: "
                f"{format_value(value)}"
            )

        lines.append(
            " | ".join(parts)
        )

    return (
        f"{task.title()}:\n"
        + "\n".join(lines)
    )


# =========================================================
# CLOSE DATABASE
# =========================================================

def close_database():

    try:

        cursor.close()

    except Exception:

        pass

    try:

        connection.close()

    except Exception:

        pass