-- No Mathlib import needed; define Set inline
def Set (G : Type) := G → Prop
namespace Set
def mem {G : Type} (s : Set G) (x : G) : Prop := s x
end Set
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
    simp only [mypow, Nat.add_zero]
    rw [Γ.e_right]
  | succ k ih =>
    simp only [mypow]
    rw [show m.add k = m + k from rfl, ih, Γ.assoc]


-- Inverse of a product: (a · b)⁻¹ = b⁻¹ · a⁻¹.
theorem inv_op {G : Type} (Γ : MyGroup G) (a b : G) :
    Γ.inv (Γ.op a b) = Γ.op (Γ.inv b) (Γ.inv a) := by
    exact (inverse_unique Γ (Γ.op a b) (Γ.op (Γ.inv b) (Γ.inv a))
      (calc Γ.op (Γ.op a b) (Γ.op (Γ.inv b) (Γ.inv a))
          = Γ.op a (Γ.op b (Γ.op (Γ.inv b) (Γ.inv a))) := Γ.assoc a b _
        _ = Γ.op a (Γ.op (Γ.op b (Γ.inv b)) (Γ.inv a)) := by rw [← Γ.assoc b (Γ.inv b) (Γ.inv a)]
        _ = Γ.op a (Γ.op Γ.e (Γ.inv a)) := by rw [Γ.inv_right b]
        _ = Γ.op a (Γ.inv a) := by rw [Γ.e_left]
        _ = Γ.e := Γ.inv_right a)).symm

-- Solving equations: if a · x = b, then x = a⁻¹ · b.
theorem solve_left {G : Type} (Γ : MyGroup G)
    (a b x : G) (h : Γ.op a x = b) : x = Γ.op (Γ.inv a) b := by
  rw [← h]
  rw [← Γ.assoc (Γ.inv a) a x]
  rw [Γ.inv_left]
  rw [Γ.e_left]

-- Right cancellation law: b · a = c · a ⇒ b = c.
theorem right_cancel {G : Type} (Γ : MyGroup G)
    (a b c : G) (h : Γ.op b a = Γ.op c a) : b = c :=
  calc b = Γ.op b Γ.e := (Γ.e_right b).symm
    _ = Γ.op b (Γ.op a (Γ.inv a)) := by rw [Γ.inv_right]
    _ = Γ.op (Γ.op b a) (Γ.inv a) := (Γ.assoc b a (Γ.inv a)).symm
    _ = Γ.op (Γ.op c a) (Γ.inv a) := by rw [h]
    _ = Γ.op c (Γ.op a (Γ.inv a)) := Γ.assoc c a (Γ.inv a)
    _ = Γ.op c Γ.e := by rw [Γ.inv_right]
    _ = c := Γ.e_right c


-- Double inverse: (a⁻¹)⁻¹ = a.
theorem inv_inv {G : Type} (Γ : MyGroup G)
    (a : G) :
    Γ.inv (Γ.inv a) = a := by
    exact (inverse_unique Γ (Γ.inv a) a (Γ.inv_left a)).symm


-- Identity inverse: e⁻¹ = e.
theorem inv_e {G : Type} (Γ : MyGroup G) :
    Γ.inv Γ.e = Γ.e := by
    exact (inverse_unique Γ Γ.e Γ.e (Γ.e_right Γ.e)).symm


-- Power successor on the left:
-- a^(n+1) = a · a^n.
theorem pow_succ_left {G : Type} (Γ : MyGroup G)
    (a : G) (n : Nat) :
    mypow Γ a (n + 1) = Γ.op a (mypow Γ a n) := by
  induction n with
  | zero => simp only [mypow]; rw [Γ.e_left, Γ.e_right]
  | succ k ih =>
    simp only [mypow]
    rw [← Γ.assoc, ← ih]
    simp only [mypow]



-- Power multiplication law:
-- (a^m)^n = a^(m*n).
theorem pow_mul {G : Type} (Γ : MyGroup G)
    (a : G) (m n : Nat) :
    mypow Γ (mypow Γ a m) n = mypow Γ a (m * n) := by
        induction n with
  | zero => simp [mypow]
  | succ k ih => simp only [mypow, Nat.mul_succ]; rw [ih, ← pow_add]



-- Commuting elements distribute over powers.
theorem commute_pow {G : Type} (Γ : MyGroup G)
    (a b : G)
    (h : Γ.op a b = Γ.op b a)
    (n : Nat) :
    Γ.op (mypow Γ a n) b =
    Γ.op b (mypow Γ a n) := by
        induction n with
  | zero => simp [mypow, Γ.e_left, Γ.e_right]
  | succ k ih =>
    simp only [mypow]
    calc Γ.op (Γ.op (mypow Γ a k) a) b
        = Γ.op (mypow Γ a k) (Γ.op a b) := Γ.assoc _ _ _
      _ = Γ.op (mypow Γ a k) (Γ.op b a) := by rw [h]
      _ = Γ.op (Γ.op (mypow Γ a k) b) a := (Γ.assoc _ _ _).symm
      _ = Γ.op (Γ.op b (mypow Γ a k)) a := by rw [ih]
      _ = Γ.op b (Γ.op (mypow Γ a k) a) := Γ.assoc _ _ _




-- ─────────────────────────────────────────────────────────────────────
-- Stage 2 — Subgroups and homomorphisms
-- Structural constructions on top of the group axioms.
-- ─────────────────────────────────────────────────────────────────────

-- A subgroup of G.
structure MySubgroup {G : Type} (Γ : MyGroup G) where
  carrier : Set G
  e_mem : carrier Γ.e
  op_closed :
    ∀ {a b : G},
      carrier a →
      carrier b →
      carrier (Γ.op a b)
  inv_closed :
    ∀ {a : G},
      carrier a →
      carrier (Γ.inv a)


-- Membership notation for subgroups.
def MySubgroup.mem {G : Type} {Γ : MyGroup G}
    (H : MySubgroup Γ) (a : G) : Prop :=
  H.carrier a


-- Intersection of two subgroups is a subgroup.
def subgroup_intersection {G : Type}
    {Γ : MyGroup G}
    (H K : MySubgroup Γ) :
    MySubgroup Γ := by
    exact {
    carrier := fun x => H.carrier x ∧ K.carrier x,
    e_mem := ⟨H.e_mem, K.e_mem⟩,
    op_closed := fun ha hb => ⟨H.op_closed ha.1 hb.1, K.op_closed ha.2 hb.2⟩,
    inv_closed := fun ha => ⟨H.inv_closed ha.1, K.inv_closed ha.2⟩
  }


-- Cyclic subgroup generated by an element.
def cyclic_subgroup {G : Type}
    (Γ : MyGroup G)
    (a : G) : Set G :=
  fun x => ∃ n : Nat, x = mypow Γ a n


-- Group homomorphisms
structure MyHom {G H : Type}
    (ΓG : MyGroup G)
    (ΓH : MyGroup H) where
  toFun : G → H
  map_op :
    ∀ a b : G,
      toFun (ΓG.op a b) =
      ΓH.op (toFun a) (toFun b)


-- ─────────────────────────────────────────────────────────────────────
-- Stage 3 — Homomorphisms, kernel, image, cosets, normality
-- The structural toolkit for the next round of theorems.
-- ─────────────────────────────────────────────────────────────────────

-- Homomorphisms preserve identity.
theorem hom_map_e {G H : Type}
    (ΓG : MyGroup G)
    (ΓH : MyGroup H)
    (φ : MyHom ΓG ΓH) :
    φ.toFun ΓG.e = ΓH.e := by
  have h : ΓH.op (φ.toFun ΓG.e) (φ.toFun ΓG.e) = ΓH.op (φ.toFun ΓG.e) ΓH.e := by
    rw [← φ.map_op, ΓG.e_left, ΓH.e_right]
  exact left_cancel ΓH (φ.toFun ΓG.e) (φ.toFun ΓG.e) ΓH.e h


-- Homomorphisms preserve inverses.
theorem hom_map_inv {G H : Type}
    (ΓG : MyGroup G)
    (ΓH : MyGroup H)
    (φ : MyHom ΓG ΓH)
    (a : G) :
    φ.toFun (ΓG.inv a) =
    ΓH.inv (φ.toFun a) := by
  apply inverse_unique
  rw [← φ.map_op, ΓG.inv_right, hom_map_e ΓG ΓH φ]


-- Composition of homomorphisms.
def hom_comp {A B C : Type}
    {ΓA : MyGroup A}
    {ΓB : MyGroup B}
    {ΓC : MyGroup C}
    (φ : MyHom ΓA ΓB)
    (ψ : MyHom ΓB ΓC) :
    MyHom ΓA ΓC :=
  { toFun := fun a => ψ.toFun (φ.toFun a),
    map_op := fun a b => by
      simp only [φ.map_op, ψ.map_op] }


-- Identity homomorphism.
def hom_id {G : Type}
    (Γ : MyGroup G) :
    MyHom Γ Γ :=
  { toFun := fun x => x,
    map_op := fun _ _ => rfl }


-- Kernel of a homomorphism.
def hom_kernel {G H : Type}
    {ΓG : MyGroup G}
    {ΓH : MyGroup H}
    (φ : MyHom ΓG ΓH) : Set G :=
  fun x => φ.toFun x = ΓH.e


-- Image of a homomorphism.
def hom_image {G H : Type}
    {ΓG : MyGroup G}
    {ΓH : MyGroup H}
    (φ : MyHom ΓG ΓH) : Set H :=
  fun y => ∃ x : G, φ.toFun x = y


-- Kernel is a subgroup.
def kernel_subgroup {G H : Type}
    {ΓG : MyGroup G}
    {ΓH : MyGroup H}
    (φ : MyHom ΓG ΓH) :
    MySubgroup ΓG :=
  { carrier := hom_kernel φ,
    e_mem := hom_map_e ΓG ΓH φ,
    op_closed := fun {a b} ha hb => by
      simp only [hom_kernel] at *
      rw [φ.map_op, ha, hb, ΓH.e_left],
    inv_closed := fun {a} ha => by
      simp only [hom_kernel] at *
      rw [hom_map_inv ΓG ΓH φ, ha, inv_e ΓH] }


-- A subgroup generated by closure under products/inverses.
-- (Stub: the smallest set containing S, closed under op and inv.
-- Inductive characterization is acceptable.)
def subgroup_generated_by {G : Type}
    (Γ : MyGroup G)
    (S : Set G) : Set G :=
  fun x => ∀ (H : MySubgroup Γ), (∀ s : G, S s → H.carrier s) → H.carrier x


-- Left coset of a subgroup.
def left_coset {G : Type}
    {Γ : MyGroup G}
    (H : MySubgroup Γ)
    (a : G) : Set G :=
  fun x => ∃ h : G,
    H.carrier h ∧
    x = Γ.op a h


-- Normal subgroup.
def normal_subgroup {G : Type}
    (Γ : MyGroup G)
    (H : MySubgroup Γ) : Prop :=
  ∀ g h : G,
    H.carrier h →
    H.carrier
      (Γ.op
        (Γ.op g h)
        (Γ.inv g))


-- ─────────────────────────────────────────────────────────────────────
-- Stage 4 — Major structural theorems
-- The subgroup criterion plus the first homomorphism toolkit.
-- ─────────────────────────────────────────────────────────────────────

-- Subgroup criterion: a nonempty subset closed under a · b⁻¹ is a subgroup.
-- Historically important: compresses identity, closure, and
-- inverse-closure into one algebraic condition.
def subgroup_criterion {G : Type} (Γ : MyGroup G)
    (S : Set G)
    (witness : G)
    (witness_mem : S witness)
    (closed : ∀ a b : G, S a → S b → S (Γ.op a (Γ.inv b))) :
    MySubgroup Γ :=
  { carrier := S,
    e_mem := by
      have := closed witness witness witness_mem witness_mem
      rwa [Γ.inv_right] at this,
    op_closed := fun {a b} ha hb => by
      have hinvb : S (Γ.inv b) := by
        have he : S Γ.e := by
          have := closed witness witness witness_mem witness_mem
          rwa [Γ.inv_right] at this
        have := closed Γ.e b he hb
        rwa [Γ.e_left] at this
      have := closed a (Γ.inv b) ha hinvb
      rwa [inv_inv] at this,
    inv_closed := fun {a} ha => by
      have he : S Γ.e := by
        have := closed witness witness witness_mem witness_mem
        rwa [Γ.inv_right] at this
      have := closed Γ.e a he ha
      rwa [Γ.e_left] at this }


-- Image of a homomorphism is a subgroup of the codomain.
def image_subgroup {G H : Type}
    {ΓG : MyGroup G}
    {ΓH : MyGroup H}
    (φ : MyHom ΓG ΓH) :
    MySubgroup ΓH :=
  { carrier := hom_image φ,
    e_mem := ⟨ΓG.e, hom_map_e ΓG ΓH φ⟩,
    op_closed := fun {a b} ⟨x, hx⟩ ⟨y, hy⟩ => ⟨ΓG.op x y, by rw [φ.map_op, hx, hy]⟩,
    inv_closed := fun {a} ⟨x, hx⟩ => ⟨ΓG.inv x, by rw [hom_map_inv ΓG ΓH φ, hx]⟩ }


-- A function is injective.
def Injective {G H : Type} (f : G → H) : Prop :=
  ∀ a b : G, f a = f b → a = b


-- A homomorphism is injective iff its kernel is trivial.
theorem hom_injective_iff_kernel_trivial {G H : Type}
    {ΓG : MyGroup G}
    {ΓH : MyGroup H}
    (φ : MyHom ΓG ΓH) :
    Injective φ.toFun ↔ ∀ x : G, hom_kernel φ x → x = ΓG.e := by
  constructor
  · intro hinj x hx
    apply hinj
    simp only [hom_kernel] at hx
    rw [hx, hom_map_e ΓG ΓH φ]
  · intro htriv a b hab
    have : hom_kernel φ (ΓG.op a (ΓG.inv b)) := by
      simp only [hom_kernel]
      rw [φ.map_op, hom_map_inv ΓG ΓH φ, hab, ΓH.inv_right]
    have heq := htriv _ this
    exact right_cancel ΓG (ΓG.inv b) a b (by rw [heq, ← ΓG.inv_right b])


-- Composition of homomorphisms is associative at the underlying-function level.
theorem hom_comp_assoc {A B C D : Type}
    {ΓA : MyGroup A}
    {ΓB : MyGroup B}
    {ΓC : MyGroup C}
    {ΓD : MyGroup D}
    (φ : MyHom ΓA ΓB)
    (ψ : MyHom ΓB ΓC)
    (χ : MyHom ΓC ΓD) :
    (hom_comp (hom_comp φ ψ) χ).toFun =
    (hom_comp φ (hom_comp ψ χ)).toFun := by
  rfl


-- ─────────────────────────────────────────────────────────────────────
-- Stage 5 (future) — Cosets as equivalence, Lagrange, quotients
-- Not stubbed yet: cosets-as-partition requires an equivalence-relation
-- abstraction (Setoid / Quotient or a hand-rolled equivalent), and
-- Lagrange's theorem needs finite-cardinality machinery. Next agenda
-- after Stage 4 lands.
-- ─────────────────────────────────────────────────────────────────────
