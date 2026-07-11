"""Safe expression parser for policy rule match expressions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


class ExpressionError(ValueError):
    """Raised when an expression cannot be parsed or evaluated."""


@dataclass(frozen=True)
class _Token:
    kind: str
    value: str | None = None


_TOKEN_RE = re.compile(
    r'\s*(?P<TOKEN>'
    r'"(?:[^"\\]|\\.)*"|'
    r"'(?:[^'\\]|\\.)*'|"
    r"!=|==|>=|<=|&&|\|\||[()\[\]!,><=]|"
    r"[a-zA-Z_][a-zA-Z0-9_.]*|"
    r"[0-9]+(?:\.[0-9]+)?"
    r")",
    re.DOTALL,
)


_KEYWORDS = {"startsWith", "contains", "matches", "in"}


def _tokenize(source: str) -> list[_Token]:
    pos = 0
    tokens: list[_Token] = []
    while pos < len(source):
        match = _TOKEN_RE.match(source, pos)
        if not match:
            raise ExpressionError(
                f"Unexpected token at position {pos}: {source[pos:pos + 20]!r}"
            )
        raw = match.group("TOKEN")
        pos = match.end()
        if raw in {"(", ")", "[", "]", "!", "&&", "||", "==", "!=", ">", ">=", "<", "<=", ","}:
            tokens.append(_Token(raw))
        elif raw[0] in {'"', "'"}:
            tokens.append(_Token("STRING", raw[1:-1]))
        elif re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", raw):
            tokens.append(_Token("NUMBER", raw))
        elif raw in _KEYWORDS:
            tokens.append(_Token("OP", raw))
        else:
            tokens.append(_Token("IDENT", raw))
    return tokens


class _Parser:
    def __init__(self, tokens: list[_Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    def _peek(self) -> _Token | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _consume(self, kind: str | None = None, value: str | None = None) -> _Token:
        token = self._peek()
        if token is None:
            raise ExpressionError("Unexpected end of expression")
        if kind and token.kind != kind:
            raise ExpressionError(f"Expected {kind}, got {token.kind}")
        if value and token.value != value and token.kind != value:
            raise ExpressionError(f"Expected {value}, got {token}")
        self.pos += 1
        return token

    def parse(self) -> "_AstNode":
        node = self._parse_or()
        if self._peek() is not None:
            raise ExpressionError("Unexpected trailing tokens in expression")
        return node

    def _parse_or(self) -> "_AstNode":
        node = self._parse_and()
        while self._peek() and self._peek().kind == "||":
            self._consume("||")
            node = _BinaryOp("||", node, self._parse_and())
        return node

    def _parse_and(self) -> "_AstNode":
        node = self._parse_unary()
        while self._peek() and self._peek().kind == "&&":
            self._consume("&&")
            node = _BinaryOp("&&", node, self._parse_unary())
        return node

    def _parse_unary(self) -> "_AstNode":
        if self._peek() and self._peek().kind == "!":
            self._consume("!")
            return _UnaryOp("!", self._parse_unary())
        return self._parse_comparison()

    def _parse_comparison(self) -> "_AstNode":
        node = self._parse_postfix()
        token = self._peek()
        if token and token.kind in {"==", "!=", ">", ">=", "<", "<="}:
            self._consume(token.kind)
            return _BinaryOp(token.kind, node, self._parse_postfix())
        return node

    def _parse_postfix(self) -> "_AstNode":
        node = self._parse_primary()
        while self._peek() and self._peek().kind == "OP":
            op = self._consume("OP").value
            if op not in {"startsWith", "contains", "matches", "in"}:
                raise ExpressionError(f"Unsupported operator {op}")
            node = _BinaryOp(op, node, self._parse_primary())
        return node

    def _parse_primary(self) -> "_AstNode":
        token = self._peek()
        if token is None:
            raise ExpressionError("Unexpected end of expression")
        if token.kind == "STRING":
            self._consume("STRING")
            return _Literal(token.value)
        if token.kind == "NUMBER":
            self._consume("NUMBER")
            return _Literal(float(token.value) if "." in token.value else int(token.value))
        if token.kind == "[":
            return self._parse_list()
        if token.kind == "IDENT":
            self._consume("IDENT")
            path = [token.value or ""]
            while self._peek() and self._peek().kind == "IDENT" and "." in (self._peek().value or ""):
                break
            while self._peek() and self._peek().kind == ".":
                self._consume(".")
                next_token = self._consume("IDENT")
                path.append(next_token.value or "")
            if len(path) == 1 and "." in path[0]:
                path = path[0].split(".")
            return _Path(path)
        if token.kind == "(":
            self._consume("(")
            node = self._parse_or()
            self._consume(")")
            return node
        raise ExpressionError(f"Unexpected token {token}")

    def _parse_list(self) -> "_AstNode":
        self._consume("[")
        values: list[Any] = []
        if self._peek() and self._peek().kind != "]":
            values.append(self._parse_primary().evaluate({}))
            while self._peek() and self._peek().kind == ",":
                self._consume(",")
                values.append(self._parse_primary().evaluate({}))
        self._consume("]")
        return _Literal(values)


class _AstNode:
    def evaluate(self, bindings: dict[str, Any]) -> Any:
        raise NotImplementedError


class _Literal(_AstNode):
    def __init__(self, value: Any) -> None:
        self.value = value

    def evaluate(self, bindings: dict[str, Any]) -> Any:
        _ = bindings
        return self.value


class _Path(_AstNode):
    def __init__(self, parts: list[str]) -> None:
        self.parts = parts
        self.dotted = ".".join(parts)

    def evaluate(self, bindings: dict[str, Any]) -> Any:
        if self.dotted in bindings:
            return bindings[self.dotted]
        current: Any = bindings
        for part in self.parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return ""
        if current is None:
            return ""
        return current


class _UnaryOp(_AstNode):
    def __init__(self, op: str, operand: _AstNode) -> None:
        self.op = op
        self.operand = operand

    def evaluate(self, bindings: dict[str, Any]) -> bool:
        value = self.operand.evaluate(bindings)
        if self.op == "!":
            return not bool(value)
        raise ExpressionError(f"Unsupported unary operator {self.op}")


class _BinaryOp(_AstNode):
    def __init__(self, op: str, left: _AstNode, right: _AstNode) -> None:
        self.op = op
        self.left = left
        self.right = right

    def evaluate(self, bindings: dict[str, Any]) -> Any:
        if self.op == "&&":
            return bool(self.left.evaluate(bindings)) and bool(self.right.evaluate(bindings))
        if self.op == "||":
            return bool(self.left.evaluate(bindings)) or bool(self.right.evaluate(bindings))
        if self.op == "startsWith":
            left = self.left.evaluate(bindings)
            right = self.right.evaluate(bindings)
            return str(left or "").startswith(str(right or ""))
        if self.op == "contains":
            left = self.left.evaluate(bindings)
            right = self.right.evaluate(bindings)
            return str(right or "") in str(left or "")
        if self.op == "matches":
            left = self.left.evaluate(bindings)
            right = self.right.evaluate(bindings)
            return re.search(str(right or ""), str(left or "")) is not None
        if self.op == "in":
            left = self.left.evaluate(bindings)
            right = self.right.evaluate(bindings)
            if isinstance(right, (list, tuple, set)):
                return left in right
            return False

        left = self.left.evaluate(bindings)
        right = self.right.evaluate(bindings)
        if self.op == "==":
            return _compare_equal(left, right)
        if self.op == "!=":
            return not _compare_equal(left, right)
        if self.op == ">":
            return left > right
        if self.op == ">=":
            return left >= right
        if self.op == "<":
            return left < right
        if self.op == "<=":
            return left <= right
        raise ExpressionError(f"Unsupported binary operator {self.op}")


def _compare_equal(left: Any, right: Any) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if isinstance(left, (int, float)) and isinstance(right, str):
        try:
            return left == float(right)
        except ValueError:
            return str(left) == right
    if isinstance(right, (int, float)) and isinstance(left, str):
        try:
            return float(left) == right
        except ValueError:
            return left == str(right)
    return left == right


class Expression:
    """Compiled policy expression."""

    def __init__(self, source: str, ast: _AstNode) -> None:
        self.source = source
        self._ast = ast

    @classmethod
    def parse(cls, source: str) -> Expression:
        """Parse an expression string into a compiled form."""
        if not source or not source.strip():
            raise ExpressionError("Expression must not be empty")
        tokens = _tokenize(source.strip())
        ast = _Parser(tokens).parse()
        return cls(source.strip(), ast)

    def evaluate(self, bindings: dict[str, Any]) -> bool:
        """Evaluate expression against bound variables."""
        return bool(self._ast.evaluate(bindings))
