-- A group defined from scratch, without Mathlib's `Group` typeclass.
-- All four group axioms are explicit fields of the structure.

structure MyGroup (G : Type) where
  op : G → G → G
  e : G
  inv : G → G
  assoc : ∀ a b c : G, op (op a b) c = op a (op b c)
  e_left : ∀ a : G, op e a = a
  e_right : ∀ a : G, op a e = a
  inv_left : ∀ a : G, op (inv a) a = e
  inv_right : ∀ a : G, op a (inv a) = e

-- If e' acts as a left identity, then e' equals the canonical identity.
theorem identity_unique {G : Type} (Γ : MyGroup G)
    (e' : G) (h : ∀ a : G, Γ.op e' a = a) : e' = Γ.e := by
  have : e' = Γ.op e' Γ.e := (Γ.e_right e').symm
  rw [this, h]

-- If b acts as a right inverse of a, then b equals the canonical inverse.
theorem inverse_unique {G : Type} (Γ : MyGroup G)
    (a b : G) (h : Γ.op a b = Γ.e) : b = Γ.inv a := by
  calc b = Γ.op Γ.e b := (Γ.e_left b).symm
    _ = Γ.op (Γ.op (Γ.inv a) a) b := by rw [Γ.inv_left]
    _ = Γ.op (Γ.inv a) (Γ.op a b) := Γ.assoc (Γ.inv a) a b
    _ = Γ.op (Γ.inv a) Γ.e := by rw [h]
    _ = Γ.inv a := Γ.e_right (Γ.inv a)

-- Left cancellation law: a · b = a · c ⇒ b = c.
theorem left_cancel {G : Type} (Γ : MyGroup G)
    (a b c : G) (h : Γ.op a b = Γ.op a c) : b = c := by
  calc b = Γ.op Γ.e b := (Γ.e_left b).symm
    _ = Γ.op (Γ.op (Γ.inv a) a) b := by rw [Γ.inv_left]
    _ = Γ.op (Γ.inv a) (Γ.op a b) := Γ.assoc (Γ.inv a) a b
    _ = Γ.op (Γ.inv a) (Γ.op a c) := by rw [h]
    _ = Γ.op (Γ.op (Γ.inv a) a) c := (Γ.assoc (Γ.inv a) a c).symm
    _ = Γ.op Γ.e c := by rw [Γ.inv_left]
    _ = c := Γ.e_left c

-- ─────────────────────────────────────────────────────────────────────
-- Stage 1 — Algebraic manipulation inside a group
-- Powers, exponent laws, inverse formulas, and solving equations.
-- ─────────────────────────────────────────────────────────────────────

-- a^n: the group operation applied n times, with the new factor
-- appended on the right. a^0 = e by convention.
def mypow {G : Type} (Γ : MyGroup G) (a : G) : Nat → G
  | 0     => Γ.e
  | n + 1 => Γ.op (mypow Γ a n) a

-- Laws of exponents: a^(m + n) = a^m · a^n.
theorem pow_add {G : Type} (Γ : MyGroup G) (a : G) (m n : Nat) :
    mypow Γ a (m + n) = Γ.op (mypow Γ a m) (mypow Γ a n) := by
  induction n with
  | zero =>
    simp [mypow, Γ.e_right]
  | succ k ih =>
    simp only [mypow, Nat.add_succ]
    rw [ih, Γ.assoc]

-- Inverse of a product: (a · b)⁻¹ = b⁻¹ · a⁻¹.
theorem inv_op {G : Type} (Γ : MyGroup G) (a b : G) :
    Γ.inv (Γ.op a b) = Γ.op (Γ.inv b) (Γ.inv a) := by
  apply (inverse_unique Γ (Γ.op a b) (Γ.op (Γ.inv b) (Γ.inv a))).symm
  calc Γ.op (Γ.op a b) (Γ.op (Γ.inv b) (Γ.inv a))
      = Γ.op a (Γ.op b (Γ.op (Γ.inv b) (Γ.inv a))) := Γ.assoc a b _
    _ = Γ.op a (Γ.op (Γ.op b (Γ.inv b)) (Γ.inv a)) := by rw [← Γ.assoc b (Γ.inv b) (Γ.inv a)]
    _ = Γ.op a (Γ.op Γ.e (Γ.inv a)) := by rw [Γ.inv_right b]
    _ = Γ.op a (Γ.inv a) := by rw [Γ.e_left]
    _ = Γ.e := Γ.inv_right a

-- Solving equations: if a · x = b, then x = a⁻¹ · b.
theorem solve_left {G : Type} (Γ : MyGroup G)
    (a b x : G) (h : Γ.op a x = b) : x = Γ.op (Γ.inv a) b := by
  rw [← h]
  rw [← Γ.assoc (Γ.inv a) a x]
  rw [Γ.inv_left]
  rw [Γ.e_left]
