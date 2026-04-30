# INFPROG2 — Python for a Senior C# Developer

> A condensed, opinionated summary of the ZHAW *INFPROG2* course (FS26) — built from the lecture notebooks, PDFs, sample code and praktika in the two zipfiles in this workspace. Written for someone who already understands OOP, types, async and build tooling from C#, and just wants to learn Python **efficiently**.

---

## 0. How to read this document

- Each section starts with a **"C# mental model"** sentence. Skip it once you've internalised the difference.
- **[!]** marks things that bit students in the course or are genuine Python-only gotchas.
- **[Nice]** marks small idioms that are disproportionately useful.
- Every week (SW1…SW14) of the course maps to a section; use §1 as a map.

---

## 1. Course map at a glance

| Week | Topic | What's actually new vs. C# |
|---|---|---|
| SW1 | Return to Python, P01 Primes | Recap: f-strings, list comp, `pow(a,b,mod)`, `is_prime`, sieve. |
| SW2 | OOP — custom types | `__init__`, `self`, `@property`, dunder methods, dataclasses. |
| SW3 | Inheritance | `super()`, MRO / C3 linearisation, `@abstractmethod`. |
| SW4 | Case study with OOP | Putting classes together in a realistic app. |
| SW5 | Files, HTTP, APIs (P03) | `with open`, `requests.Session`, retries, encoding. |
| SW6 | Validation & integrity | Pydantic at boundaries, `assert` vs `raise`, fuzzy matching, mutable-default trap. |
| SW7 | Dataframes (P04) | Pandas: `loc` vs `iloc`, groupby, merge. |
| SW8 | Data processing | NumPy vectorisation, broadcasting, multiprocessing. |
| SW9 | Data management case study | Text analysis, currency exchange, scraping. |
| SW10 | Testing & tuning | `unittest` / `pytest`, `black`, `flake8`, `mypy`, type hints, pre-commit. |
| SW11 | Sorting & complexity I | Big-O, bubble/insertion/selection, Timsort. |
| SW12 | Sorting & complexity II | Merge sort, quick sort, recursion. |
| SW13 | Performance optimisation | `timeit`, `cProfile`, `lru_cache`, hashing. |
| SW14 | Recap & practice | Fuzzy word search case study. |

**Praktika**: P01 Match game + Classroom + BankAccount, P02 Inheritance (SavingAccount / YouthAccount / TaxReport), P03 Online data (currencies, flaky BOM service), P04 DataFrames statistics app. The **semester project** (see §15) is an alternative replacing all four.

---

## 2. C# → Python quick cheat sheet

| C# | Python | Note |
|---|---|---|
| `namespace` | file = module, folder + `__init__.py` = package | No declaration, filename *is* the name. |
| `using (var f = ...) { }` | `with open(...) as f:` | Works with any object implementing `__enter__/__exit__`. |
| `this` | `self` (explicit first parameter) | Mandatory, visible, must be passed to base calls in some patterns. |
| `public`/`private`/`protected` | nothing / `_name` / `__name` | Convention, not enforced. `__` triggers **name mangling**, not privacy. |
| Interface | `abc.ABC` + `@abstractmethod` *or* `typing.Protocol` (structural) | Duck typing is the default — just call the method. |
| `null` | `None` | Compare with `is None`, never `== None`. |
| `?.` / `??` | `x if x is not None else default`, or `x or default` (careful with 0 / "") | No null-conditional operator. |
| `var` | no-op — everything is dynamic | Add **type hints** for tooling: `x: int = 3`. |
| `async`/`await` | `async def` / `await`, run via `asyncio.run(...)` | Cooperative, single-thread. See §10 for the GIL. |
| `List<T>`, `Dict<K,V>` | `list[T]`, `dict[K, V]` (3.9+) | Built-ins are generic; old `List[int]` from `typing` is legacy. |
| LINQ `Select`/`Where` | list/gen comprehension `[f(x) for x in xs if pred(x)]` | Faster and idiomatic. |
| `IEnumerable` lazy | **generator** `(f(x) for x in xs)` or `yield` | Memory-efficient streams. |
| `Nullable<T>` | `T | None` or `Optional[T]` | Pipe syntax is 3.10+. |
| `dynamic` | normal variable | Everything is dynamic. |
| `throw new X("msg")` | `raise X("msg")` | |
| `try/catch/finally` | `try/except/else/finally` | `else` runs only if no exception. |
| NuGet | pip + `requirements.txt` *or* poetry/uv + `pyproject.toml` | Virtual env per project. |
| `dotnet format` | `black` (no config) + `ruff`/`flake8` | `black` is uncompromising, that's the point. |
| `dotnet test` | `pytest` (or `unittest`) | pytest discovers `test_*.py` automatically. |

---

## 3. Fast-track Python quirks a C# dev must know on day 1

1. **Indentation is syntax.** No braces. 4 spaces, never tabs. `black` enforces it.
2. **Objects are always passed by reference.** `def f(lst): lst.append(1)` mutates the caller's list. Use `list.copy()` / `copy.deepcopy()` when you don't want that.
3. **Mutable default arguments are shared** between calls. `def f(xs=[])` creates **one** list at *def time*, not per call. Always use `def f(xs=None): xs = xs or []` or `dataclasses.field(default_factory=list)`. **[!]**
4. **`is` vs `==`**: `is` tests identity (same object), `==` tests equality. Use `is` only for `None`, `True`, `False`.
5. **`0.1 + 0.2 != 0.3`** — IEEE-754 same as C#. For comparisons use `math.isclose`; for money use `decimal.Decimal`.
6. **Everything is an object** — functions, classes, modules. You can assign them, pass them, attach attributes to them.
7. **Truthiness is broad**: `0`, `""`, `[]`, `{}`, `None`, `False` are all falsy. `if xs:` is the idiomatic "not empty" check.
8. **Encoding is not auto-detected.** Always pass `encoding="utf-8"` to `open` and `pd.read_csv`. **[!]**
9. **GIL**: threads do not parallelise CPU work. Use `multiprocessing` or `concurrent.futures.ProcessPoolExecutor` for CPU-bound; `asyncio` or threads only for I/O-bound.
10. **Assertions can be disabled with `python -O`.** Never rely on them for runtime invariants — use `raise ValueError(...)` instead. **[!]**

---

## 4. Syntax survival kit

```python
# f-strings — the only string formatter you need
name, n = "Ada", 3
f"{name} has {n} items, {n*n=}"          # 'Ada has 3 items, n*n=9'
f"|{3.14159:>10.2f}|"                     # right-align, 2 decimals
f"|{42:010d}|"                            # '|0000000042|'

# sequence unpacking
a, b, *rest = [1, 2, 3, 4, 5]             # rest == [3, 4, 5]
x, y = y, x                               # swap

# comprehensions
squares   = [x*x for x in range(10)]              # list
even_sq   = [x*x for x in range(10) if x%2 == 0]  # filter
lookup    = {w: len(w) for w in words}            # dict
unique    = {c for c in "abracadabra"}            # set
lazy_gen  = (x*x for x in range(10_000_000))      # generator — O(1) memory

# zip / enumerate / sorted
for i, name in enumerate(names, start=1): ...
for a, b in zip(xs, ys): ...
sorted(students, key=lambda s: s.grade, reverse=True)

# slicing — [start:stop:step], stop exclusive
xs[::-1]   # reverse
xs[:3]     # first 3
xs[-2:]    # last 2

# truthy / None idioms
x = d.get("key", default)                 # never KeyError
cfg = user_cfg or DEFAULTS                # None/empty → defaults
```

---

## 5. OOP (SW2–SW4) — the meat of the course

### 5.1 Class skeleton

```python
from __future__ import annotations  # forward-references free

class BankAccount:
    """IBAN-ish account with balance and currency."""

    MAX_BALANCE: float = 100_000.0     # class attribute (static in C#)

    def __init__(self, iban: str, currency: str = "CHF") -> None:
        self.iban = iban                # public-by-convention
        self._balance = 0.0             # "protected" — don't touch from outside
        self.__closed = False           # name-mangled to _BankAccount__closed
        self.currency = currency

    # instance method
    def deposit(self, amount: float) -> None:
        if amount <= 0:
            raise ValueError("amount must be positive")
        if self._balance + amount > self.MAX_BALANCE:
            raise ValueError("balance cap exceeded")
        self._balance += amount

    # property — looks like an attribute, runs code
    @property
    def balance(self) -> float:
        return self._balance

    # class method — factory pattern (alternative constructors)
    @classmethod
    def empty(cls, iban: str) -> "BankAccount":
        return cls(iban)

    # static method — no self, no cls; just namespacing
    @staticmethod
    def is_valid_iban(iban: str) -> bool:
        return iban.isalnum() and len(iban) >= 5

    # dunders — see §5.4
    def __repr__(self) -> str:
        return f"BankAccount(iban={self.iban!r}, balance={self._balance})"
```

**Key C#-vs-Python points**

- `self` is **explicit** and mandatory in every method. `obj.deposit(10)` is compiled by the interpreter as `BankAccount.deposit(obj, 10)`.
- Attributes don't need to be declared at class level. Anything you write to `self.foo` creates it. Declaring at class level creates a **class attribute** shared by all instances (be careful with mutable ones).
- No method overloading. The second `def f(...)` silently replaces the first. Use default args, `*args/**kwargs`, or `functools.singledispatch`.

### 5.2 Properties — Python's way of getters/setters

```python
class Threshold:
    def __init__(self, v: float = 0.5) -> None:
        self.value = v                          # goes through setter

    @property
    def value(self) -> float: return self._v

    @value.setter
    def value(self, v: float) -> None:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"expected [0,1], got {v}")
        self._v = v

    @property
    def complement(self) -> float:              # read-only
        return 1.0 - self._v
```

Callers write `t.value = 0.7` — looks like assignment, runs validation. `@cached_property` (from `functools`) caches the first computed value on the instance.

### 5.3 Dataclasses — the `POCO` shortcut

```python
from dataclasses import dataclass, field

@dataclass(slots=True, frozen=True)
class Point:
    x: float
    y: float
    tags: list[str] = field(default_factory=list)   # NEVER `= []`
```

You get `__init__`, `__repr__`, `__eq__` for free. `frozen=True` makes it immutable. `slots=True` saves memory and blocks attribute typos. **[Nice]** for values and DTOs; drop back to a handwritten class when you need custom behaviour.

### 5.4 Dunder (magic) methods cheat-sheet

| Dunder | Triggered by | Use |
|---|---|---|
| `__init__`, `__repr__`, `__str__` | construction, `repr()`, `print()` | Always write `__repr__`. |
| `__eq__`, `__hash__` | `==`, dict/set keys | If you define `__eq__`, set `__hash__ = None` or define it too. |
| `__lt__` + `@functools.total_ordering` | `<`, `<=`, `>`, `>=`, `sorted()` | Save boilerplate. |
| `__add__`, `__sub__`, `__mul__`, `__rmul__` | `+ - * *` | Return `NotImplemented` (sentinel) if types don't match — don't raise. |
| `__len__`, `__getitem__`, `__setitem__`, `__iter__`, `__contains__` | `len()`, `x[i]`, `for`, `in` | Implement these and your class "is" a collection. |
| `__enter__`, `__exit__` | `with` | Resource management. |
| `__call__` | `obj(...)` | Callable objects (e.g., parametrised transformers). |

### 5.5 Inheritance, `super()`, MRO

```python
class DataSet:
    def __init__(self, values: list[float], name: str = "unnamed") -> None:
        self.values = values
        self.name = name

class LabeledDataSet(DataSet):
    def __init__(self, values: list[float], labels: list[str], name: str = "unnamed") -> None:
        super().__init__(values, name)          # always call the base
        self.labels = labels
```

- **Parent `__init__` is never called automatically.** Forgetting `super().__init__()` is the #1 OOP bug in the course. **[!]**
- Multiple inheritance is allowed; Python computes a linear **Method Resolution Order** using C3 linearisation. Inspect with `Cls.__mro__`.
- Always use `super().__init__(...)` — the cooperative form — not `Parent.__init__(self, ...)`. Direct parent calls break the chain in diamond inheritance.

### 5.6 Abstract base classes

```python
from abc import ABC, abstractmethod

class FeatureTransformer(ABC):
    @abstractmethod
    def fit(self, xs: list[float]) -> None: ...
    @abstractmethod
    def transform(self, xs: list[float]) -> list[float]: ...

    def fit_transform(self, xs: list[float]) -> list[float]:
        self.fit(xs); return self.transform(xs)
```

Instantiating a subclass that hasn't implemented every `@abstractmethod` raises `TypeError`. For purely structural typing (C# interfaces-by-shape), use `typing.Protocol` instead.

### 5.7 Encapsulation reality check

```python
class C:
    def __init__(self):
        self.public = 1
        self._protected = 2   # convention: "don't touch from outside"
        self.__private = 3    # name-mangled to _C__private — still reachable

c = C()
c._C__private  # 3  — Python trusts you
```

No enforcement. The course's P01 BankAccount relies on this: you **choose** to route mutation through `deposit()`/`withdraw()`; the language won't help.

### 5.8 References, not values — the aliasing trap

```python
a = [1, 2, 3]
b = a            # same list, not a copy
b.append(4)
a                # [1, 2, 3, 4]

b = a[:]         # shallow copy
import copy
b = copy.deepcopy(a)  # nested copy
```

C# developers expect this for reference types, but Python applies it uniformly — including list slicing results that share nested objects. V06's `references.py` / `references_oop.py` drills this.

---

## 6. Files & I/O (SW5)

```python
# reading text
with open("data.txt", encoding="utf-8") as f:
    text = f.read()
    # or: for line in f: process(line)   — streams, doesn't load whole file

# CSV — prefer pandas; use csv module for tiny/streaming cases
import csv
with open("people.csv", encoding="utf-8", newline="") as f:   # newline="" on Windows!
    for row in csv.DictReader(f):
        print(row["name"], row["age"])

# JSON
import json
data = json.loads(text)                                    # str -> obj
json.dump(data, open("out.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)

# pickle — Python's BinaryFormatter. Never unpickle untrusted data. [!]
import pickle
pickle.dump(obj, open("x.pkl", "wb"))
```

**Encoding pitfalls**

- Windows Excel often writes `cp1252`, not UTF-8. **[!]**
- Always pass `encoding="utf-8"`. Catch `UnicodeDecodeError` and retry with `"cp1252"` / `"latin1"` as fallback for user data.
- On Windows, pass `newline=""` to `open()` when using the `csv` module or you'll get blank lines.

---

## 7. HTTP & APIs (SW5, P03)

### 7.1 Minimal request

```python
import requests

r = requests.get("https://api.example.com/data",
                 params={"lat": 47.4, "lon": 8.5},
                 timeout=20)             # ALWAYS set a timeout [!]
r.raise_for_status()
data = r.json()
```

### 7.2 Production pattern — session + retries + backoff

```python
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=5, backoff_factor=0.5,
                  status_forcelist=[429, 500, 502, 503, 504],
                  allowed_methods=["GET", "HEAD"])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://",  HTTPAdapter(max_retries=retry))
    return s
```

This is what P03 expects for the "flaky BOM service" (exponential backoff + tolerance to missing/broken records).

### 7.3 Cache with file-age (P04)

```python
import os, time, json, pathlib
def cached_fetch(url: str, cache: pathlib.Path, ttl: int = 600) -> dict:
    if cache.exists() and time.time() - cache.stat().st_mtime < ttl:
        return json.loads(cache.read_text("utf-8"))
    data = requests.get(url, timeout=20).json()
    cache.write_text(json.dumps(data), encoding="utf-8")
    return data
```

### 7.4 Beyond JSON

- **XML**: `xml.etree.ElementTree` (watch out for namespaces — `findall(".//ns:x", {"ns": "..."})`).
- **HTML tables**: `pd.read_html(url)` → list of DataFrames. Shockingly useful.
- **CSV response**: `pd.read_csv(io.StringIO(r.text))`.

---

## 8. Validation & robustness (SW6)

- **Boundary** (user input, external APIs, files) → validate loudly. Use **Pydantic** `BaseModel` with `Field(...)` constraints and `@field_validator`. Produces typed, sanitised objects or raises `ValidationError` with a per-field report.
- **Internal** (your own trusted code) → use plain `@dataclass` or simple classes.
- Don't use `assert` for business rules — it disappears with `-O`.
- For fuzzy matching user input against a vocabulary: `difflib.get_close_matches(word, vocab, n=1, cutoff=0.6)`; or `SequenceMatcher.ratio()` for a similarity score. V06 uses this for typo correction.

```python
from pydantic import BaseModel, Field, EmailStr, field_validator

class DatasetIn(BaseModel):
    dataset_id: int = Field(gt=0)
    name: str = Field(min_length=3)
    email: EmailStr
    tier: str

    @field_validator("name")
    @classmethod
    def normalise(cls, v: str) -> str:
        return "_".join(v.strip().lower().split())

    @field_validator("tier")
    @classmethod
    def check_tier(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in {"bronze", "silver", "gold"}:
            raise ValueError("tier must be bronze/silver/gold")
        return v
```

---

## 9. Pandas (SW7, P04)

**Mental model**: a DataFrame is a dict of columns where each column is a typed NumPy array, plus a row Index. It is **not** a list of row objects — think in columns, not rows.

```python
import pandas as pd

df = pd.read_csv("data.csv", encoding="utf-8")
df.head(); df.tail(); df.info(); df.describe(); df.dtypes
df.shape                     # (rows, cols)
```

### 9.1 `.loc` vs `.iloc` — the one thing you must memorise

```python
df.loc[3, "name"]            # label-based: inclusive end in slices
df.loc[df.age > 25, "salary"] = 70_000   # mutate in place, correctly

df.iloc[3, 0]                # positional: exclusive end, like NumPy
df.iloc[0:2, 1:3]
```

**[!] Never chain `df[mask]["col"] = value`** — since pandas 3.0 it silently fails under Copy-on-Write. Always `df.loc[mask, "col"] = value`.

### 9.2 Transform / filter / aggregate

```python
df.query("age > 25 and salary < 60000")
df[df["category"].isin(["A", "B"])]

df.groupby("category").agg(
    total=("value", "sum"),
    avg=("value", "mean"),
    n=("value", "count"),
)

pd.merge(left, right, on="id", how="inner")   # SQL-style joins
pd.concat([df1, df2], axis=0)                 # stack rows
df.pivot_table(values="sales", index="date", columns="region", aggfunc="sum")
df.melt(id_vars="date", value_vars=["temp_zh", "temp_ge"])
```

### 9.3 Missing values

- `NaN` (float) — default pandas missing marker.
- `pd.NA` — new, dtype-neutral; nullable types `Int64`, `boolean`, `string`.
- `df.isna()`, `df.dropna(subset=[...])`, `df.fillna(0)` / `df.ffill()`.

### 9.4 Plotting

```python
df.plot(x="date", y="price", kind="line", title="…")
df["category"].value_counts().plot(kind="bar")
```

P04 requires at least one such visualisation.

---

## 10. NumPy & parallelism (SW8)

```python
import numpy as np
a = np.arange(12).reshape(3, 4)         # 3x4 matrix
a.sum(axis=0)                           # column sums
a.mean(axis=1)                          # row means
a[a > 5]                                # boolean filter
a @ a.T                                 # matrix multiply
```

**Vectorise, don't loop.** `arr * 2 + 1` is one call into C; `[x*2+1 for x in arr]` is thousands of Python-level calls and 50–200× slower. Broadcasting extends smaller arrays along missing dimensions — no copy is made.

### 10.1 The GIL and concurrency

| Workload | Tool |
|---|---|
| CPU-bound (pure Python) | `concurrent.futures.ProcessPoolExecutor` — real parallelism, one process per core. |
| CPU-bound (NumPy/pandas) | Often already parallel internally; otherwise `ProcessPoolExecutor`. |
| I/O-bound (HTTP, disk) | `asyncio` + `aiohttp` or `ThreadPoolExecutor`. GIL releases on syscalls, so threads help here. |

```python
from concurrent.futures import ProcessPoolExecutor

if __name__ == "__main__":          # required on Windows [!]
    with ProcessPoolExecutor() as ex:
        results = list(ex.map(heavy_fn, inputs))
```

---

## 11. Decorators (SW10) — understand these once, use them everywhere

```python
import functools, time

def timed(func):
    @functools.wraps(func)          # preserve __name__ / __doc__
    def wrapper(*args, **kw):
        t0 = time.perf_counter()
        try:    return func(*args, **kw)
        finally:
            print(f"{func.__name__} took {time.perf_counter()-t0:.4f}s")
    return wrapper

@timed
def slow():
    time.sleep(0.1)
```

Decorator-factory (parameterised):

```python
def retry(n=3, delay=0.1):
    def deco(func):
        @functools.wraps(func)
        def wrap(*a, **kw):
            for i in range(n):
                try: return func(*a, **kw)
                except Exception:
                    if i == n - 1: raise
                    time.sleep(delay * 2**i)
        return wrap
    return deco
```

**Must-know built-ins**

- `@property`, `@staticmethod`, `@classmethod`
- `@functools.cached_property` — compute-once-per-instance
- `@functools.lru_cache(maxsize=128)` / `@functools.cache` — memoisation. Naive `fib(35)` goes from ~1.5 s to <1 ms. **[Nice]**
- `@functools.total_ordering`
- `@dataclass`
- `@contextlib.contextmanager` — turn a generator into a context manager
- `@pytest.fixture`, `@pytest.mark.parametrize`

Stacking is bottom-up at *decoration* time:
```python
@bold
@upper
def greet(): return "hello"
# equivalent to: greet = bold(upper(greet))
```

---

## 12. Testing (SW10)

### 12.1 unittest (stdlib, what the course uses)

```python
import unittest

class TestMath(unittest.TestCase):
    def setUp(self):    self.xs = [1, 2, 3]
    def test_sum(self): self.assertEqual(sum(self.xs), 6)
    def test_raises(self):
        with self.assertRaises(ValueError):
            int("abc")

if __name__ == "__main__":
    unittest.main()
```

### 12.2 pytest (recommended in industry) — convention over config

```python
# tests/test_math.py
import pytest

@pytest.fixture
def xs(): return [1, 2, 3]

def test_sum(xs): assert sum(xs) == 6

@pytest.mark.parametrize("s,n", [("a", 1), ("abc", 3)])
def test_len(s, n): assert len(s) == n
```

Run: `pytest -q`.

### 12.3 `assert` vs `raise`

- **`assert`** — developer-facing invariants, disabled with `-O`. Use in tests and internal sanity checks.
- **`raise ValueError / TypeError / RuntimeError`** — production errors, always live. Use for user input, state invariants, contract violations.

---

## 13. Code quality, type hints, packaging (SW10)

### 13.1 Type hints (ignored at runtime, consumed by `mypy`, IDEs)

```python
from __future__ import annotations
from typing import Protocol, Iterable, Literal, Final

PI: Final[float] = 3.14159

def mean(xs: list[float]) -> float: ...
def head(xs: Iterable[int], n: int = 5) -> list[int]: ...
Direction = Literal["N", "E", "S", "W"]

class Renderable(Protocol):           # structural "interface"
    def render(self) -> str: ...
```

**[!] NumPy gotcha**: `np.int32(5)` is *not* `int` to `mypy`. Use `int(...)`, `numpy.typing.NDArray[np.float64]`, or `# type: ignore[...]` locally.

### 13.2 Tooling stack

| Tool | Role | Run |
|---|---|---|
| `black` | Auto-format, 88-col, zero config | `black .` |
| `ruff` or `flake8` | Lint (style + bugs) | `ruff check .` |
| `isort` (or `ruff --fix`) | Sort imports | |
| `mypy` | Static type check | `mypy src` |
| `pytest` + `coverage` | Tests | `pytest --cov` |
| `pre-commit` | Run all of the above on commit | `pre-commit install` once |

Configure in `pyproject.toml`:

```toml
[tool.black]
line-length = 88
target-version = ["py311"]

[tool.mypy]
python_version = "3.11"
ignore_missing_imports = true
warn_return_any = true
```

### 13.3 Virtual environments

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r requirements.txt
pip freeze > requirements.txt
```

Never install project dependencies globally.

---

## 14. Algorithms, sorting, performance (SW11–SW13)

- Python's built-in `sorted()` / `list.sort()` is **Timsort**: O(n log n) worst-case, O(n) on already-sorted data, **stable**.
- Sort with a key: `sorted(people, key=lambda p: (p.city, -p.age))` — tuples give lexicographic multi-key sort; the minus inverts that key.
- The course covers bubble/insertion/selection/merge/quicksort for Big-O reasoning, not because you'd ever hand-roll them.
- **Hashing**: `dict`/`set` are open-addressing hash tables, O(1) average lookup. Keys must be hashable (immutable) — so `list` and `dict` are invalid keys but `tuple` of hashables is fine.
- **Memoisation**: `@functools.lru_cache` converts exponential recursion to linear. Required in P01 primes for large inputs.
- **Profiling**:

```python
import timeit, cProfile, pstats
timeit.timeit("f()", globals=globals(), number=1000)

cProfile.run("run_app()", "out.prof")
pstats.Stats("out.prof").sort_stats("cumulative").print_stats(20)
```

- Jupyter has `%time` and `%timeit` magics — use `%timeit` for repeatable measurements.

---

## 15. Praktika & semester project — what you actually have to deliver

### P01 (SW1–SW2)
- **Match game** (Nim-style): stack of 10–20 matches; players take 1–3; last one loses. Computer plays a deterministic strategy. Procedural OK.
- **Classroom objects**: model a teacher + 20 docs + 10 tables × 2 students — pure modelling exercise.
- **Person**: attributes + behaviours (`speak`, `grow_older`).
- **BankAccount**: IBAN-like ID, currency (default CHF), `deposit`/`withdraw`, balance in `[0, 100_000]`, open/close, `if __name__ == "__main__"` test guard. Extended in P02–P03.

### P02 (SW3)
- `SavingAccount(BankAccount)` — 0.1 %/month interest, allows negative balance, 2 % overdraft fee.
- `YouthAccount(BankAccount)` — 2 %/month, ages 0–25, 2 000/month withdrawal cap.
- `BankApplication` — auth, multi-account menu, `current_account` pointer.
- `TaxReport.generate(bank_app)` — prints totals per account type.
- Simulate time: 1 month ≡ 10 s of wall clock (`time.sleep`).

### P03 (SW5)
- Currency-exchange module with caching; open any currency, tax-report converts to CHF.
- Flaky BOM service at `http://160.85.252.61:32101` — no parameters, returns text; must handle failures (exponential backoff), broken records, mis-encoded umlauts; output `MAT | COST` table with sum.

### P04 (SW7)
- Pandas-based statistics app on a public tabular dataset (e.g., opendata.swiss).
- **File-age cache** with 10 min TTL (hint: `os.stat`).
- Compute statistics (mean/var/skew/kurtosis or counts) + at least one visualisation.
- ≥ 2 classes (main app + downloader).

### Semester project (alternative to P01–P04, 20 pts = 20 % of grade)
- 1–2 people. **Registration deadline 01.03.2026** (just names by email; topic optional then).
- Real-world data app in Python, must include:
  - **OOP**: 2–3 meaningful classes, inheritance where appropriate (4 pts).
  - **Internet data**: at least one public API, fetched programmatically (4 pts).
  - **Robustness & validation**: try/except, retries, malformed data survival (shares OOP slot).
  - **Pandas analysis + visualisation** (4 pts).
  - **Code quality**: ≥ 3 meaningful unit tests, clean structure, readable (4 pts).
  - **Presentation**: 5–10 min in last lab session, both members must explain any line (4 pts).
- Deliver as Git repo: `src/`, `notebooks/`, `tests/`, README, demo notebook/script.
- AI tools explicitly allowed but you must explain every line. Blind copy-paste = deductions. **[!]**

Example project ideas from the guide: Open-Meteo weather analyser, transport-delay tracker (transport.opendata.ch), Hacker News/Reddit keyword tracker, opendata.swiss explorer, crypto/stock tracker with moving averages.

---

## 16. Practical advice (the stuff that actually saves you time)

1. **Start every file with `from __future__ import annotations`** — forward refs and `list[int]` work on older Pythons too.
2. **One venv per project. Commit `requirements.txt` / `pyproject.toml`, not `.venv/`.**
3. **Set up `black` + `ruff` + `mypy` + `pytest` on day one** and wire them into pre-commit. Learning habits stick when the tooling enforces them.
4. **Type-hint everything** (the course rules require it anyway per your global style). `mypy` finds real bugs.
5. **Write `__repr__` for every class you make.** Debugging improves 10×.
6. **Prefer list/dict comprehensions over `map` / `filter`.** They're faster and more Pythonic.
7. **Use `pathlib.Path`, not string concatenation** for filesystem work: `Path("data") / "x.csv"`.
8. **Default to `with open(...)`** — the file is closed even on exceptions, no `try/finally`.
9. **In pandas, always `.loc[mask, col] = value`.** Chained assignment is now a silent bug.
10. **Always pass `timeout=` to `requests.get/post`.** Without it a hung server hangs your program forever. **[!]**
11. **Always pass `encoding="utf-8"` to `open` and `read_csv`.** Don't trust the OS default — especially on Windows. **[!]**
12. **Use `copy.deepcopy`** when passing nested structures into things that might mutate them.
13. **`if __name__ == "__main__":`** at the bottom of every module you might import — keeps import free of side effects.
14. **For recursion**, slap `@functools.lru_cache` on the function before you optimise anything else.
15. **For Jupyter**, prefer `%pip install …` inside the notebook, **not** `!pip install …` — uses the kernel's env.
16. **Save trained/fitted objects with `pickle` only for trusted contexts**, `joblib` for sklearn, `json` for data you might read elsewhere.
17. **Name mangling (`__x`)** is only useful to avoid name clashes in subclasses, not for privacy. Use `_x` for "don't touch".
18. **Don't use `and`/`or` like C#'s `&`/`|` on pandas/numpy** — `(df.a > 1) & (df.b < 2)`, parentheses required, short-circuit logic doesn't work there. **[!]**
19. **Remember `else` on loops**: `for x in xs: ... else: ...` runs if the loop did not `break`. Niche but elegant for "search and handle not-found".
20. **The REPL is your compiler.** `python -i script.py`, `ipython`, or a Jupyter kernel should be open while you work. Try expressions interactively.

---

## 17. Suggested learning order (most efficient path)

Given your C# background, most lectures will feel familiar. Prioritise where Python is **different**:

1. **Week 1 day — tooling**: install Python 3.11+, set up `venv`, VS Code / PyCharm, `black` + `ruff` + `mypy` + `pytest`, pre-commit. Skim V01.
2. **Day 2 — OOP dunder mechanics**: V02 notebook. Write a container class with `__len__`, `__iter__`, `__getitem__`, `__eq__`, `__repr__`. You won't re-learn this.
3. **Day 3 — Inheritance + properties**: V03 notebook, redo P01 BankAccount and P02 sub-accounts.
4. **Day 4 — Files, HTTP, validation**: V05/V06 notebooks. Do P03 — it consolidates everything that differs from C#.
5. **Day 5 — Pandas + NumPy**: V07/V08 notebooks + `V08_numpy_pandas_practice.ipynb`. Work problems, don't just read.
6. **Day 6 — Decorators, tests, type hints**: V10 notebook. Re-visit your P01–P03 code, add type hints and tests.
7. **Weekend — Semester project scaffolding**: pick a topic, stand up the repo with tooling, write the first class, the first HTTP fetch with caching, the first test. You'll coast through the rest of the semester.

---

## 18. Files in this workspace worth reading first

Ranked by "hours-of-learning-per-minute-spent":

1. `Jupyter Notebooks/V10_devtools_decorators_ds.ipynb` — venv, black, flake8, mypy, decorators, `lru_cache`.
2. `Jupyter Notebooks/V02_oop_custom_types_ds.ipynb` + `V03_oop_inheritance_ds.ipynb` + `V09_oop_magic_args_ds.ipynb`.
3. `Jupyter Notebooks/V05_online_data_io_ds.ipynb` + `V06_validation_orm_alternative.ipynb`.
4. `Labs Solutions/P01_bankaccount.py`, `P02_bankaccount.py`, `P02_inheritance.py` — the reference OOP patterns the course expects.
5. `prog2_main/Allgemeines/code/V06_references.py` / `V06_references_oop.py` — the aliasing trap, in your face.
6. `prog2_main/Allgemeines/code/V10_badcode.py` vs `V10_testing.py` — "before/after" for linter/tests.
7. `Jupyter Notebooks/V08_numpy_pandas_ds.ipynb` + `Labs Solutions/V08_numpy_pandas_practice.ipynb`.
8. `oneway_primes.py` + `P01_Primes.pdf` — recursion, memoisation, modular arithmetic in ~150 lines.

Everything is under `_extracted/` in this workspace after the zips are unpacked.
