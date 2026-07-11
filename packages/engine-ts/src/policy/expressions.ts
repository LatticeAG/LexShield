export class ExpressionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ExpressionError';
  }
}

export type ExpressionBindings = Record<string, unknown>;

type Token =
  | { type: 'string'; value: string }
  | { type: 'number'; value: number }
  | { type: 'ident'; value: string }
  | { type: 'op'; value: string }
  | { type: 'keyword'; value: string }
  | { type: 'lparen' }
  | { type: 'rparen' }
  | { type: 'lbracket' }
  | { type: 'rbracket' }
  | { type: 'comma' }
  | { type: 'eof' };

type Expr =
  | { kind: 'literal'; value: string | number | unknown[] }
  | { kind: 'ident'; name: string }
  | { kind: 'unary'; op: '!'; arg: Expr }
  | { kind: 'binary'; op: string; left: Expr; right: Expr };

const KEYWORDS = new Set(['in', 'startsWith', 'contains', 'matches']);

function tokenize(source: string): Token[] {
  const tokens: Token[] = [];
  let index = 0;

  while (index < source.length) {
    const char = source[index]!;
    if (/\s/.test(char)) {
      index += 1;
      continue;
    }

    if (char === '"' || char === "'") {
      const quote = char;
      let value = '';
      index += 1;
      while (index < source.length) {
        const current = source[index]!;
        if (current === '\\' && index + 1 < source.length) {
          value += source[index + 1];
          index += 2;
          continue;
        }
        if (current === quote) {
          index += 1;
          break;
        }
        value += current;
        index += 1;
      }
      tokens.push({ type: 'string', value });
      continue;
    }

    if (/[0-9]/.test(char) || (char === '.' && index + 1 < source.length && /[0-9]/.test(source[index + 1]!))) {
      let raw = '';
      while (index < source.length && /[0-9.]/.test(source[index]!)) {
        raw += source[index]!;
        index += 1;
      }
      const value = Number(raw);
      if (Number.isNaN(value)) {
        throw new ExpressionError(`Invalid number literal: ${raw}`);
      }
      tokens.push({ type: 'number', value });
      continue;
    }

    const twoChar = source.slice(index, index + 2);
    if (['&&', '||', '==', '!=', '>=', '<='].includes(twoChar)) {
      tokens.push({ type: 'op', value: twoChar });
      index += 2;
      continue;
    }

    if ('()[],!><'.includes(char)) {
      switch (char) {
        case '(':
          tokens.push({ type: 'lparen' });
          break;
        case ')':
          tokens.push({ type: 'rparen' });
          break;
        case '[':
          tokens.push({ type: 'lbracket' });
          break;
        case ']':
          tokens.push({ type: 'rbracket' });
          break;
        case ',':
          tokens.push({ type: 'comma' });
          break;
        case '!':
        case '>':
        case '<':
          tokens.push({ type: 'op', value: char });
          break;
      }
      index += 1;
      continue;
    }

    if (/[a-zA-Z_]/.test(char)) {
      let ident = '';
      while (index < source.length && /[a-zA-Z0-9_.]/.test(source[index]!)) {
        ident += source[index]!;
        index += 1;
      }
      if (KEYWORDS.has(ident)) {
        tokens.push({ type: 'keyword', value: ident });
      } else {
        tokens.push({ type: 'ident', value: ident });
      }
      continue;
    }

    throw new ExpressionError(`Unexpected character in expression: ${char}`);
  }

  tokens.push({ type: 'eof' });
  return tokens;
}

class Parser {
  private index = 0;

  constructor(private readonly tokens: Token[]) {}

  parse(): Expr {
    const expr = this.parseOr();
    if (this.peek().type !== 'eof') {
      throw new ExpressionError('Unexpected tokens after expression');
    }
    return expr;
  }

  private parseOr(): Expr {
    let left = this.parseAnd();
    while (this.matchOp('||')) {
      const right = this.parseAnd();
      left = { kind: 'binary', op: '||', left, right };
    }
    return left;
  }

  private parseAnd(): Expr {
    let left = this.parseUnary();
    while (this.matchOp('&&')) {
      const right = this.parseUnary();
      left = { kind: 'binary', op: '&&', left, right };
    }
    return left;
  }

  private parseUnary(): Expr {
    if (this.matchOp('!')) {
      return { kind: 'unary', op: '!', arg: this.parseUnary() };
    }
    return this.parseComparison();
  }

  private parseComparison(): Expr {
    let left = this.parsePostfix();
    const next = this.peek();

    if (next.type === 'op' && ['==', '!=', '>', '>=', '<', '<='].includes(next.value)) {
      this.advance();
      const right = this.parsePostfix();
      return { kind: 'binary', op: next.value, left, right };
    }

    return left;
  }

  private parsePostfix(): Expr {
    let left = this.parsePrimary();
    const next = this.peek();

    if (next.type === 'keyword' && KEYWORDS.has(next.value)) {
      const op = next.value;
      this.advance();
      const right = this.parsePrimary();
      return { kind: 'binary', op, left, right };
    }

    return left;
  }

  private parsePrimary(): Expr {
    const token = this.peek();

    if (token.type === 'string') {
      this.advance();
      return { kind: 'literal', value: token.value };
    }

    if (token.type === 'number') {
      this.advance();
      return { kind: 'literal', value: token.value };
    }

    if (token.type === 'ident') {
      this.advance();
      return { kind: 'ident', name: token.value };
    }

    if (token.type === 'lparen') {
      this.advance();
      const expr = this.parseOr();
      if (this.peek().type !== 'rparen') {
        throw new ExpressionError('Expected closing parenthesis');
      }
      this.advance();
      return expr;
    }

    if (token.type === 'lbracket') {
      this.advance();
      const values: unknown[] = [];
      if (this.peek().type !== 'rbracket') {
        do {
          values.push(this.evalLiteralValue(this.parsePrimary()));
          if (this.peek().type === 'comma') {
            this.advance();
            continue;
          }
          break;
        } while (this.peek().type !== 'rbracket');
      }
      if (this.peek().type !== 'rbracket') {
        throw new ExpressionError('Expected closing bracket');
      }
      this.advance();
      return { kind: 'literal', value: values };
    }

    throw new ExpressionError(`Unexpected token in expression: ${token.type}`);
  }

  private evalLiteralValue(expr: Expr): string | number {
    if (expr.kind === 'literal') {
      if (typeof expr.value === 'string' || typeof expr.value === 'number') {
        return expr.value;
      }
    }
    if (expr.kind === 'ident') {
      return expr.name;
    }
    throw new ExpressionError('List literals may only contain strings or numbers');
  }

  private peek(): Token {
    return this.tokens[this.index] ?? { type: 'eof' };
  }

  private advance(): Token {
    const token = this.peek();
    this.index += 1;
    return token;
  }

  private matchOp(value: string): boolean {
    const token = this.peek();
    if (token.type === 'op' && token.value === value) {
      this.advance();
      return true;
    }
    return false;
  }
}

function resolveIdent(name: string, bindings: ExpressionBindings): unknown {
  if (Object.prototype.hasOwnProperty.call(bindings, name)) {
    return bindings[name];
  }

  const parts = name.split('.');
  let current: unknown = bindings;
  for (const part of parts) {
    if (current && typeof current === 'object' && !Array.isArray(current)) {
      current = (current as Record<string, unknown>)[part];
    } else {
      return '';
    }
  }

  return current ?? '';
}

function compareEqual(left: unknown, right: unknown): boolean {
  if (typeof left === 'number' && typeof right === 'number') {
    return left === right;
  }
  if (typeof left === 'number' && typeof right === 'string') {
    const parsed = Number(right);
    return !Number.isNaN(parsed) && left === parsed;
  }
  if (typeof right === 'number' && typeof left === 'string') {
    const parsed = Number(left);
    return !Number.isNaN(parsed) && parsed === right;
  }
  return left === right;
}

function evalExpr(expr: Expr, bindings: ExpressionBindings): unknown {
  switch (expr.kind) {
    case 'literal':
      return expr.value;
    case 'ident':
      return resolveIdent(expr.name, bindings);
    case 'unary': {
      const value = evalExpr(expr.arg, bindings);
      return !Boolean(value);
    }
    case 'binary': {
      if (expr.op === '||') {
        return Boolean(evalExpr(expr.left, bindings)) || Boolean(evalExpr(expr.right, bindings));
      }
      if (expr.op === '&&') {
        return Boolean(evalExpr(expr.left, bindings)) && Boolean(evalExpr(expr.right, bindings));
      }
      if (expr.op === 'startsWith') {
        const left = evalExpr(expr.left, bindings);
        const right = evalExpr(expr.right, bindings);
        return String(left ?? '').startsWith(String(right ?? ''));
      }
      if (expr.op === 'contains') {
        const left = evalExpr(expr.left, bindings);
        const right = evalExpr(expr.right, bindings);
        return String(right ?? '') !== '' && String(left ?? '').includes(String(right ?? ''));
      }
      if (expr.op === 'matches') {
        const left = evalExpr(expr.left, bindings);
        const right = evalExpr(expr.right, bindings);
        try {
          return new RegExp(String(right ?? '')).test(String(left ?? ''));
        } catch {
          return false;
        }
      }
      if (expr.op === 'in') {
        const left = evalExpr(expr.left, bindings);
        const right = evalExpr(expr.right, bindings);
        if (!Array.isArray(right)) {
          return false;
        }
        return right.some((item) => compareEqual(item, left));
      }

      const left = evalExpr(expr.left, bindings);
      const right = evalExpr(expr.right, bindings);
      switch (expr.op) {
        case '==':
          return compareEqual(left, right);
        case '!=':
          return !compareEqual(left, right);
        case '>':
          return (left as number) > (right as number);
        case '>=':
          return (left as number) >= (right as number);
        case '<':
          return (left as number) < (right as number);
        case '<=':
          return (left as number) <= (right as number);
        default:
          throw new ExpressionError(`Unsupported operator: ${expr.op}`);
      }
    }
    default:
      throw new ExpressionError('Invalid expression node');
  }
}

export class Expression {
  readonly source: string;
  private readonly ast: Expr;

  private constructor(source: string, ast: Expr) {
    this.source = source;
    this.ast = ast;
  }

  static parse(source: string): Expression {
    if (!source || !source.trim()) {
      throw new ExpressionError('Expression must not be empty');
    }
    const trimmed = source.trim();
    const tokens = tokenize(trimmed);
    const parser = new Parser(tokens);
    const ast = parser.parse();
    return new Expression(trimmed, ast);
  }

  evaluate(bindings: ExpressionBindings): boolean {
    return Boolean(evalExpr(this.ast, bindings));
  }
}

function stringifyArg(value: unknown): string {
  if (typeof value === 'boolean') {
    return value ? 'true' : 'false';
  }
  if (typeof value === 'number') {
    return String(value);
  }
  if (value === null || value === undefined) {
    return '';
  }
  return String(value);
}

export function buildExpressionBindings(
  request: {
    tool: { name: string; namespace?: string };
    caller: { id: string; type: string; roles?: string[] };
    arguments: Record<string, unknown>;
    context: { environment?: string; tags?: Record<string, string> };
  },
  classifications: Array<{ intent: string; confidence: number }>,
): ExpressionBindings {
  const bindings: ExpressionBindings = {
    'tool.name': request.tool.name,
    'tool.namespace': request.tool.namespace ?? '',
    'caller.id': request.caller.id,
    'caller.type': request.caller.type,
    env: request.context.environment ?? '',
  };

  if (request.caller.roles?.length) {
    bindings['caller.roles'] = [...request.caller.roles];
  }

  if (classifications.length > 0) {
    const primary = classifications[0]!;
    bindings.intent = primary.intent;
    bindings.confidence = primary.confidence;
  }

  for (const [key, value] of Object.entries(request.context.tags ?? {})) {
    bindings[`tags.${key}`] = value;
  }

  for (const [key, value] of Object.entries(request.arguments)) {
    bindings[`args.${key}`] = stringifyArg(value);
  }

  return bindings;
}
