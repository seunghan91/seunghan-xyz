---
title: "순수 Rust로 IEEE 754 binary128을 libquadmath와 bit-exact 재현하기 — 불가능하다는 단정이 틀렸던 이유"
date: 2026-06-27T20:59:04+09:00
draft: false
tags: ["rust", "floating-point", "ieee754", "libquadmath", "ffi"]
description: "Rust f128은 nightly에 FromStr도 없으니 binary128 bit-exact는 불가능하다고 단정했다가, IEEE 754 correctly-rounded 유일성 정리로 뒤집힌 기록. 순수 Rust 파서가 libquadmath와 68,264건 byte 동치를 달성한 과정과 -0·FFI ABI 함정."
---

C++ 코드에 `__float128`(GCC 쿼드 정밀도)을 쓰는 부분을 Rust로 옮길 일이 있었다. 128비트 부동소수점, IEEE 754로는 binary128이다. `f32`/`f64`처럼 Rust 표준에 `f128`이 있긴 한데, 막상 손대보니 "이건 순수 Rust로는 못 한다"는 결론이 먼저 나왔다.

그런데 그 단정이 틀렸다. 정확히는 **반은 맞고 반은 틀렸다**. 며칠을 들여 직접 순수 Rust 파서를 만들고 6만 건 넘는 차등 퍼징으로 검증하고 나서야, "왜 안 된다고 생각했는지"와 "왜 사실은 되는지"가 둘 다 명확해졌다. 그 기록이다.

이 글에 서비스나 도메인 얘기는 없다. 순수하게 binary128, libquadmath, IEEE 754, Rust FFI 이야기만 한다.

---

## binary128과 GCC __float128, libquadmath

IEEE 754 binary128은 128비트 부동소수점이다. 부호 1비트, 지수 15비트, 가수 112비트(암묵적 선두 1 포함하면 유효 113비트). `f64`(binary64)가 가수 52비트(유효 53비트)인 것과 비교하면 정밀도가 두 배 이상이다.

GCC는 이걸 `__float128` 타입으로 노출한다. x86-64에서는 대부분 하드웨어 명령이 없어서 소프트웨어로 처리하는데, 그 런타임이 **libquadmath**다. 문자열 파싱(`strtoflt128`), 포맷(`quadmath_snprintf`), 그리고 `__addtf3`/`__multf3` 같은 compiler-rt 빌트인으로 사칙연산을 구현한다.

```c
#include <quadmath.h>
__float128 v = strtoflt128("0.1", NULL);     // 십진 문자열 → binary128
char buf[160];
quadmath_snprintf(buf, sizeof buf, "%.8Qf", v);  // binary128 → 소수 8자리
```

내 목표는 이걸 **bit-exact**로 재현하는 것이었다. 단순히 "IEEE 754를 준수"가 아니라, 같은 입력에 대해 메모리상 16바이트가 마지막 비트까지 똑같아야 했다.

---

## 처음 내린 (틀린) 단정: "순수 Rust로는 불가능"

Rust에는 `f128` 프리미티브 타입이 있다. 그래서 `"0.1".parse::<f128>()` 하면 끝날 줄 알았다. 안 된다.

```rust
#![feature(f128)]
fn main() {
    let x: f128 = "0.1".parse().unwrap();
    println!("{:.8}", x);
}
```

stable 채널에서 컴파일하면 이렇게 뜬다.

```
error[E0554]: `#![feature]` may not be used on the stable release channel
error[E0277]: the trait bound `f128: FromStr` is not satisfied
```

두 가지가 동시에 막힌다. 첫째, `f128`은 2026년 현재도 **nightly 전용 experimental**이다(tracking issue #116909, RFC 3453). stable에서는 타입 자체가 unstable(`E0658`)이다. 둘째, nightly에서 `#![feature(f128)]`를 켜도 **`FromStr`와 `Display`가 구현돼 있지 않다**(`E0277`). 즉 십진 문자열 파싱도, 포맷 출력도 표준 라이브러리로는 안 된다.

그럼 `f64`로 파싱한 다음 binary128로 넓히면 되지 않을까? 이것도 막힌다. `f64`는 가수가 53비트뿐이라, `0.1` 같은 이진 비표현 값을 binary128의 113비트 정밀도로 담을 수 없다. 실제로 해봤다. `f64`로 파싱한 뒤 비트 레이아웃만 binary128로 확장해서 libquadmath와 비교했더니:

```
입력    f64 경유                              libquadmath(binary128)
0.1     00000000000000a0999999999999fb3f    9a99999999999999999999999999fb3f
```

하위 60비트가 통째로 `0`이다. `f64`가 채우지 못한 자리다. 20개 케이스 중 6개(`0`, `1`, `-1.5`, `0.5` 같은 이진 정확 표현값)만 같고 14개가 달랐다.

여기까지 보고 "순수 Rust로는 binary128 bit-exact 불가능, libquadmath를 FFI로 부르는 수밖에 없다"고 결론냈다. **이게 틀렸다.**

---

## 정정: IEEE 754 correctly-rounded 유일성 정리

며칠 뒤 다시 들여다보다가 핵심을 놓쳤다는 걸 깨달았다. IEEE 754에는 **correctly rounded(올바르게 반올림된)** 연산이라는 개념이 있다. 어떤 연산을 "무한 정밀도로 정확히 계산한 뒤, 결과를 현재 반올림 모드로 한 번만 반올림한 값"으로 정의하면, **그 결과는 유일하다**. 구현이 무엇이든 상관없다.

IEEE 754는 다음을 correctly rounded로 **강제**한다.

| 연산 | correctly rounded? | 순수 Rust로 byte-exact 가능? |
|------|-------------------|------------------------------|
| `+`, `-`, `*`, `/` | 예 (강제) | 가능 (유일성 보장) |
| `sqrt`, `fma` | 예 (강제) | 가능 |
| 십진 → binary128 파싱 | 예 (강제) | 가능 |
| binary128 → 십진 포맷 | 예 (강제) | 가능 |
| `sin`, `cos`, `exp`, `log`, `pow` | **아니오 (비강제)** | **불가능** |

핵심은 마지막 줄이다. **초월함수(transcendental functions)는 correctly rounding을 요구하지 않는다.** 이른바 Table Maker's Dilemma 때문이다. 무한 정밀도로 sin 같은 값을 계산해서 정확히 어느 쪽으로 반올림할지 판정하려면, 경계에 임의로 가까운 입력에 대해 임의로 많은 자릿수를 계산해야 할 수 있다. 그래서 표준은 이걸 강제하지 않고, 라이브러리마다 자체 알고리즘을 쓴다. libquadmath의 `sinq`, `expq`는 그 라이브러리만의 last bit를 갖는다. 이건 그 라이브러리를 그대로 복제하지 않는 한 재현 불가다.

반대로 말하면, **파싱·포맷·사칙연산은 correctly rounded라서 유일하다**. 순수 Rust로 correctly rounded만 정확히 구현하면, libquadmath와 byte까지 똑같아야 한다. 유일성 정리가 그걸 보장한다. 안 되는 게 아니라, 그냥 직접 구현하면 된다. 다만 **그 구현이 빡세다**는 게 진짜 장벽이었던 거다.

---

## 순수 Rust로 직접 구현: big-integer + round-half-even

그래서 파싱(`strtoflt128` 대응)을 순수 Rust로 짰다. 외부 crate 0개, `std`만, FFI 없음. 알고리즘은 빅인티저 기반 correctly-rounded 변환이다.

1. 입력 십진 문자열을 부호 / 정수부 / 소수부로 쪼개서 **유리수 `P/Q`**로 만든다. `"123.456"`이면 `P = 123456`, `Q = 1000`. `"100000000000000000000"`이면 `P = 10^20`, `Q = 1`. 모두 빅인티저다.
2. `value = P/Q`를 `1.f × 2^E` 꼴로 정규화할 이진 지수 `E`를 찾는다. `Q·2^E ≤ P < Q·2^(E+1)`을 만족하는 `E`다. 비트 길이로 근사한 뒤 시프트 비교로 정밀화한다.
3. 113비트 가수 `M = round_half_even(P · 2^(112-E) / Q)`를 빅인티저 나눗셈으로 구한다. 몫과 나머지를 모두 들고 있다가, **나머지의 2배를 제수와 비교**해서 반올림한다. 크면 올림, 작으면 버림, 같으면(정확히 절반) 짝수 쪽으로(round-half-to-even).
4. 올림 캐리로 `M`이 `2^113`이 되면 `M = 2^112`, `E += 1`로 정규화한다.
5. `mantissa = M - 2^112`(112비트), `exp_field = E + 16383`(bias), `bits = sign<<127 | exp_field<<112 | mantissa`를 `u128::to_le_bytes()`로 직렬화한다.

핵심 라운딩 부분만 떼면 이런 모양이다.

```rust
// P, Q: 빅인티저(Vec<u32> LE limbs). shift = 112 - E.
// numerator = P << max(shift,0), denom = Q << max(-shift,0)
let (quotient, remainder) = div_rem(&numerator, &denom);   // 비트 단위 long division
let mut m = quotient;                                       // 113비트 후보 가수
// round-half-to-even: 2*remainder vs denom
let twice = shl1(&remainder);
match cmp(&twice, &denom) {
    Ordering::Greater => add_one(&mut m),                  // 올림
    Ordering::Less => {}                                   // 버림
    Ordering::Equal => if is_odd(&m) { add_one(&mut m); }  // 절반 → 짝수로
}
```

빅인티저는 `Vec<u32>` LE limb로 직접 구현했다. 십진 파싱용 `mul_add_small`, 시프트, 비교, 뺄셈, `set_bit`/`get_bit`/`bit_len` 정도만 있으면 된다. 값 크기가 수백 비트 규모라 비트 단위 나눗셈으로도 즉시 끝난다. 성능 최적화는 안 했다. 목표는 정확성이지 속도가 아니었으니까.

`f64`의 Rust 표준 파싱은 Eisel–Lemire 알고리즘으로 correctly rounded를 보장하는데, 이걸 113비트로 확장하는 것도 이론적으로는 같은 길이다. 다만 상수 테이블과 error bound를 전부 128비트로 다시 잡아야 해서, 그냥 느리지만 명백히 정확한 빅인티저 경로를 택했다.

---

## 검증: 68,264건 차등 퍼징

20개 케이스 통과로는 못 믿는다. correctly rounded가 정말 견고한지 보려면 대량으로 두들겨야 한다. libquadmath를 ground truth로 놓고 차등 퍼징(differential fuzzing)을 돌렸다.

ground truth는 Docker `--platform linux/amd64`로 `rockylinux:8` 컨테이너를 띄워서 만들었다. 운영에서 쓰는 RHEL 8 계열과 같은 libquadmath를 보장하려는 거다.

```bash
docker run --rm --platform linux/amd64 -v "$(pwd)":/work -w /work rockylinux:8 bash -c '
  dnf install -y gcc-c++ libquadmath-devel
  g++ -O2 -std=c++11 oracle_bulk.cpp -o oracle -lquadmath
  ./oracle fuzz_inputs.txt > golden_fuzz.csv   # 각 입력 strtoflt128 → 16바이트 hex
'
```

입력 분포는 의도적으로 라운딩 경계를 노렸다.

- **exact binary tie**: `top113·2 + 1`을 `2^z`로 민 값. round-half-even이 실제로 발동하는 핵심
- **dyadic 분수**: `K·5^f / 10^f = K / 2^f`, 이진에서 정확히 끝나는 값
- 마지막 자리가 `5`로 끝나는 십진 half 케이스
- 113비트 풀가수(유효숫자 30자리 이상), 가수 all-ones carry(`1.999…`, `2^k - 1`)
- 극한 지수(`1e30`, `1e-300` long-form), `2^52`/`2^53`/`2^112`/`2^113` 경계
- 음수, 0 근처, 무작위 십진(정수부 0~25자리 + 소수부 0~30자리)

8개 독립 seed로 반복해서 총 **68,264건**. 순수 Rust 파서로 전부 파싱해서 libquadmath의 16바이트와 비교했다. 순수 파서는 libquadmath가 필요 없으니 검증 자체는 macOS에서 `cargo test`로 돌렸다. golden CSV 파일만 있으면 된다.

```
PASS 68264/68264
```

전건 byte 동치. IEEE 754 유일성 정리가 실증된 거다. `0.1`을 다시 보면, `f64` 경유에서 `0`으로 비어 있던 하위 60비트가 이제 libquadmath와 정확히 같은 `9a99...` 패턴으로 채워진다.

---

## 함정 1: negative zero의 부호 비트

1차 퍼징에서 15,896건 중 딱 2건이 틀렸다. 둘 다 `-0.000…0` 형태, 음의 0이었다.

libquadmath는 `-0.0`을 부호 비트가 켜진 binary128(`…0080` 패턴)로 반환한다. 그런데 내 파서는 빅인티저가 0이면 부호를 따지지 않고 `[0u8; 16]`을 반환했다. 즉 `+0.0`으로 뭉갠 거다. 라운딩 결함이 아니라 **sign-of-zero** 버그였다.

```rust
// 잘못된 코드
if num.is_zero() {
    return [0u8; 16];        // 부호를 잃어버림
}
// 고친 코드
if num.is_zero() {
    let mut b = [0u8; 16];
    if sign { b[15] = 0x80; } // -0 의 부호 비트 보존
    return b;
}
```

IEEE 754에서 `+0`과 `-0`은 값으로는 같지만 비트 패턴이 다르고, `1.0 / -0.0 = -inf` 같은 데서 의미가 갈린다. bit-exact가 목표라면 부호 0도 정확히 살려야 한다. 고친 뒤 -0 포함 전건 일치.

---

## 함정 2: __float128을 by-value로 넘기는 FFI ABI

비교 대상인 libquadmath 쪽도 Rust에서 FFI로 부를 일이 있었는데, 여기서 더 고약한 걸 만났다. `strtoflt128`은 `__float128`을 by-value로 반환한다. Rust에서 이걸 16바이트 구조체로 받았다.

```rust
#[repr(C, align(16))]
struct F128([u8; 16]);

extern "C" {
    fn strtoflt128(s: *const c_char, endptr: *mut *mut c_char) -> F128;
}
```

겉보기엔 멀쩡하다. 그런데 `parse("0")`을 호출하면 결과가 이렇게 나왔다.

```
parse("0") = 00000000000000002e00000000000000
```

전부 0이어야 하는데 9번째 바이트에 `0x2e` 쓰레기가 박혀 있다. x86-64 System V ABI 때문이다. `__float128`은 **SSE 클래스**라 XMM 레지스터로 반환된다. 반면 Rust의 `#[repr(C)] struct { [u8; 16] }`는 **aggregate**로 분류돼 INTEGER 레지스터(RAX:RDX)나 메모리로 반환된다. 호출 규약이 어긋나서, 호출 측이 엉뚱한 레지스터를 읽은 거다.

해결은 by-value `__float128`을 FFI 경계에 아예 노출하지 않는 거다. C 쪽에 얇은 shim을 두고 포인터(out-param)로 16바이트를 `memcpy`한다.

```c
#include <quadmath.h>
#include <string.h>
void qm_strtoflt128(const char* s, unsigned char* out16) {
    __float128 v = strtoflt128(s, (char**)0);
    memcpy(out16, &v, 16);   // 포인터로 바이트만 복사 → ABI 분류 무관
}
```

```rust
extern "C" {
    fn qm_strtoflt128(s: *const c_char, out16: *mut u8);
}
pub fn parse(s: &str) -> [u8; 16] {
    let cs = CString::new(s).unwrap();
    let mut b = [0u8; 16];
    unsafe { qm_strtoflt128(cs.as_ptr(), b.as_mut_ptr()); }
    b
}
```

`quadmath_snprintf`도 가변인자(varargs)에 `__float128`을 넘기는 거라 같은 부류 위험이 있어서, 역시 non-varargs shim으로 감쌌다. **FFI에서 16바이트 정렬 스칼라를 by-value로 주고받을 땐 ABI 클래스를 의심해라**가 교훈이다. 작은 타입은 잘 되다가 이런 데서 조용히 깨진다.

---

## 결론: 불가능이 아니라 비용

처음의 "순수 Rust로는 binary128 bit-exact 불가능"은 부정확한 단정이었다. 정확히 다시 쓰면 이렇다.

- **파싱·포맷·사칙·sqrt·fma** = correctly rounded → IEEE 754 유일성으로 **어떤 독립 구현이든 byte-identical**. 순수 Rust로 가능하다. 68,264건이 그 증거다.
- **초월함수(sin/exp/pow/log)** = correctly rounding 비강제 → 라이브러리 고유 알고리즘이라 **순수 재현은 본질적으로 불가능**. 이것만 libquadmath를 그대로 써야 한다.

그러니 "libquadmath를 FFI로 부르라"는 권장은 *이론적으로 불가능해서*가 아니다. correctly rounded subset에 대해선 순수 Rust가 **이론적으로 가능**하다. 다만 113비트 correctly-rounded 변환을 직접 구현하고 검증하는 엔지니어링 비용이 크고, libquadmath 자체가 정말 correctly rounded인지(문서가 명시 보장하진 않는다, `sqrtq` 라운딩 버그 전례도 있었다) 신뢰해야 하는 문제가 있을 뿐이다. 초월함수가 섞이면 그땐 정말로 같은 라이브러리가 필요하다.

쓸 연산이 파싱·포맷·반올림뿐이라면 순수 Rust로 충분히 byte-exact가 나온다. "안 된다"고 단정하기 전에, 그게 *이론적 불가*인지 *구현 비용*인지부터 가르는 게 먼저였다. 관련해서 [병렬 AI 에이전트로 작업하다 만난 git worktree 함정](/posts/ai-parallel-agents-git-branch-pitfalls-worktree-pin/) 글도 비슷하게, 처음 막막해 보이던 게 결국 구조의 문제였던 기록이다.
