"""Безопасный вычислитель пользовательских вегетационных индексов.

Формат выражения (как в руководстве MultiCam, стр. 21):
  * переменные задаются как `xλ`, где λ — длина волны канала (например x650, x900);
  * операции: + - * / и скобки;
  * допускаются числовые литералы (например `0.2`, `1`).

Примеры корректных выражений:
    x650 / x900
    (x800 - x550) / x700
    1 / x550 + 1 / x850

Реализация на ast с белым списком узлов — eval() не используется, выполнение
произвольного кода невозможно.
"""
from __future__ import annotations

import ast
import operator
import re
from typing import Mapping

import numpy as np

from .. import WAVELENGTHS

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

_VAR_RE = re.compile(r"^x(\d+)$")


class CustomIndexError(ValueError):
    """Некорректное пользовательское выражение индекса."""


def _eval_node(node: ast.AST, spectrum: Mapping[int, "float | np.ndarray"]):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, spectrum)
    if isinstance(node, ast.BinOp):
        op = _OPS.get(type(node.op))
        if op is None:
            raise CustomIndexError(f"Недопустимая операция: {type(node.op).__name__}")
        return op(_eval_node(node.left, spectrum), _eval_node(node.right, spectrum))
    if isinstance(node, ast.UnaryOp):
        op = _OPS.get(type(node.op))
        if op is None:
            raise CustomIndexError("Недопустимая унарная операция")
        return op(_eval_node(node.operand, spectrum))
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise CustomIndexError(f"Недопустимая константа: {node.value!r}")
    if isinstance(node, ast.Name):
        m = _VAR_RE.match(node.id)
        if not m:
            raise CustomIndexError(
                f"Переменная '{node.id}' должна быть вида xλ (например x650)"
            )
        wl = int(m.group(1))
        if wl not in WAVELENGTHS:
            raise CustomIndexError(
                f"Канала {wl} нм нет в камере. Доступны: {list(WAVELENGTHS)}"
            )
        if wl not in spectrum:
            raise CustomIndexError(f"В спектре отсутствует канал {wl} нм")
        return spectrum[wl]
    raise CustomIndexError(f"Недопустимый элемент выражения: {type(node).__name__}")


def evaluate_custom_index(expr: str, spectrum: Mapping[int, "float | np.ndarray"]):
    """Вычисляет пользовательский индекс по спектру (скаляр или карта)."""
    expr = expr.strip()
    if not expr:
        raise CustomIndexError("Пустое выражение индекса")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise CustomIndexError(f"Синтаксическая ошибка в выражении: {exc.msg}") from exc
    return _eval_node(tree, spectrum)
