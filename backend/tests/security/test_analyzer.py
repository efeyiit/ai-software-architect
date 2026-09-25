"""Source-backed security signals; all values below are synthetic fixtures."""

import pytest

from app.analyzers.security import analyze_security
from app.parsers.python import parse_file as parse_python
from app.parsers.typescript import parse_file as parse_typescript
from app.parsers.java import parse_file as parse_java
from app.parsers.csharp import parse_file as parse_csharp
from app.parsers.cpp import parse_file as parse_cpp


def _scan(path, source, parser):
    structure = parser(path, source)
    assert structure.errors == []
    return analyze_security([structure], {path: source})


def test_python_categories_and_redacted_wire_output():
    secret = "sk_test_SyntheticNeverUse_1234567890123456"
    source = f'''import os
import jwt
API_KEY = "{secret}"
password = "fake-password-for-tests"
def load(cursor, user_id, logger):
    query = f"SELECT * FROM users WHERE id = {{user_id}}"
    cursor.execute(query)
    jwt.decode(token, options={{"verify_signature": False}})
    logger.info(password)
    return os.environ["SERVICE_SECRET"]
'''
    findings = _scan("src/service.py", source, parse_python)
    kinds = {finding.issue_type for finding in findings}
    assert {"hardcoded_secret", "dynamic_sql", "jwt_validation", "sensitive_log", "environment_secret"} <= kinds
    assert all(finding.source == "static" and finding.location.path == "src/service.py"
               and finding.location.start_line > 0 for finding in findings)
    wire = "".join(finding.model_dump_json() for finding in findings)
    assert secret not in wire
    assert "fake-password-for-tests" not in wire
    assert "SERVICE_SECRET" not in wire
    assert all("potential" in finding.description.lower() for finding in findings)


def test_python_parameterization_comments_and_verified_jwt_are_quiet():
    source = '''# password = "fake-password-for-tests"
help_text = "API_KEY = 'sk_test_SyntheticNeverUse_1234567890123456'"
cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
jwt.decode(token, key, algorithms=["HS256"])
logger.info("request complete")
value = os.getenv("SERVICE_SECRET")
'''
    assert _scan("src/safe.py", source, parse_python) == []


@pytest.mark.parametrize(("path", "source", "parser"), [
    ("src/api.ts", '''const apiKey = "fake-token-value-1234567890";
db.query(`SELECT * FROM users WHERE id = ${userId}`);
logger.info(password);
logger.info(process.env.SERVICE_SECRET);
jwt.decode(token);
''', parse_typescript),
    ("src/Api.java", '''class Api {
 String password = "fake-password-123456";
 void run(String id) {
  statement.executeQuery("SELECT * FROM users WHERE id=" + id);
  logger.info(password);
  logger.info(System.getenv("SERVICE_SECRET"));
 }
}''', parse_java),
    ("src/Api.cs", '''class Api {
 string password = "fake-password-123456";
 void Run(string id) {
  command.CommandText = "SELECT * FROM users WHERE id=" + id;
  logger.LogInformation(password);
  logger.LogInformation(Environment.GetEnvironmentVariable("SERVICE_SECRET"));
 }
}''', parse_csharp),
    ("src/api.cpp", '''#include <string>
void run(std::string id) {
 const std::string password = "fake-password-123456";
 auto query = std::string("SELECT * FROM users WHERE id=") + id;
 logger.info(password);
 logger.info(std::getenv("SERVICE_SECRET"));
}''', parse_cpp),
])
def test_other_languages_report_supported_categories_without_values(path, source, parser):
    findings = _scan(path, source, parser)
    kinds = {finding.issue_type for finding in findings}
    assert {"hardcoded_secret", "dynamic_sql", "sensitive_log", "environment_secret"} <= kinds
    wire = "".join(item.model_dump_json() for item in findings)
    assert "fake-password-123456" not in wire
    assert "SERVICE_SECRET" not in wire


def test_sensitive_explicit_public_route_only_and_middleware_abstention():
    route = '''@app.delete("/admin/users/{user_id}")
@public
def delete_user(user_id):
    return remove(user_id)
'''
    findings = _scan("src/routes.py", route, parse_python)
    assert [item.issue_type for item in findings] == ["possible_missing_auth"]
    with_middleware = '''app.add_middleware(AuthenticationMiddleware)
''' + route
    assert all(item.issue_type != "possible_missing_auth" for item in
               _scan("src/routes.py", with_middleware, parse_python))
    ordinary_route = '''@app.delete("/admin/users/{user_id}")
def delete_user(user_id):
    return remove(user_id)
'''
    assert all(item.issue_type != "possible_missing_auth" for item in
               _scan("src/routes.py", ordinary_route, parse_python))


@pytest.mark.parametrize(("path", "source", "parser"), [
    ("src/safe.ts", '''// db.query(`SELECT * FROM users WHERE id = ${userId}`)
const help = "password = 'fake-password-123456'";
const query = "SELECT * FROM users" + " WHERE active = 1";
db.query("SELECT * FROM users WHERE id = $1", [userId]);
logger.info("password");
const key = process.env.API_KEY;
jwt.verify(token, key);
''', parse_typescript),
    ("src/Safe.java", '''class Safe {
 void run(String id) {
  String query = "SELECT * FROM users" + " WHERE active = 1";
  connection.prepareStatement("SELECT * FROM users WHERE id = ?");
  logger.info("password");
  String key = System.getenv("API_KEY");
 }
}''', parse_java),
    ("src/Safe.cs", '''class Safe {
 void Run(string id) {
  var query = "SELECT * FROM users" + " WHERE active = 1";
  command.CommandText = "SELECT * FROM users WHERE id = @id";
  command.Parameters.AddWithValue("@id", id);
  logger.LogInformation("password");
  var key = Environment.GetEnvironmentVariable("API_KEY");
 }
}''', parse_csharp),
    ("src/safe.cpp", '''#include <string>
void run(std::string id) {
 auto query = std::string("SELECT * FROM users") + " WHERE active = 1";
 auto key = std::getenv("API_KEY");
 logger.info("password");
}''', parse_cpp),
])
def test_non_python_parameterization_and_inert_text_are_quiet(path, source, parser):
    assert _scan(path, source, parser) == []


def test_jwt_explicit_claim_validation_bypass_is_potential_only():
    source = 'jwt.verify(token, key, { ignoreExpiration: true });\n'
    findings = _scan("src/token.ts", source, parse_typescript)
    assert [item.issue_type for item in findings] == ["jwt_validation"]
    assert "Potential" in findings[0].description


@pytest.mark.parametrize(("path", "source", "parser"), [
    ("src/routes.ts", '''class Routes {
 @Public()
 @Delete('/admin/users')
 deleteUser() { return remove(); }
}''', parse_typescript),
    ("src/Routes.java", '''class Routes {
 @PermitAll
 @DELETE
 @Path("/admin/users")
 void deleteUser() {}
}''', parse_java),
    ("src/Routes.cs", '''class Routes {
 [AllowAnonymous]
 [HttpDelete("/admin/users")]
 public void DeleteUser() {}
}''', parse_csharp),
])
def test_explicit_public_sensitive_routes_in_framework_syntax(path, source, parser):
    findings = _scan(path, source, parser)
    assert [item.issue_type for item in findings] == ["possible_missing_auth"]


def test_cross_file_middleware_suppresses_route_signal():
    route_source = '''@app.delete("/admin/users")
@public
def delete_user():
    return remove()
'''
    middleware_source = '''app.add_middleware(AuthenticationMiddleware)
'''
    files = [parse_python("src/routes.py", route_source),
             parse_python("src/app.py", middleware_source)]
    findings = analyze_security(files, {"src/routes.py": route_source, "src/app.py": middleware_source})
    assert all(item.issue_type != "possible_missing_auth" for item in findings)


def test_snapshot_mismatch_and_parse_error():
    structure = parse_python("src/bad.py", "def broken(:\n")
    assert analyze_security([structure], {"src/bad.py": "def broken(:\n"}) == []
    with pytest.raises(ValueError, match="exactly match"):
        analyze_security([structure], {})
    invalid_secret_source = 'password = "fake-password-123456"\ndef broken(:\n'
    broken = parse_python("src/bad.py", invalid_secret_source)
    assert analyze_security([broken], {"src/bad.py": invalid_secret_source}) == []


def test_annotation_without_value_does_not_abort_security_scan():
    source = "result: str\ncursor.execute(f'SELECT * FROM users WHERE id = {user_id}')\n"
    findings = _scan("src/annotated.py", source, parse_python)
    assert [finding.issue_type for finding in findings] == ["dynamic_sql"]
