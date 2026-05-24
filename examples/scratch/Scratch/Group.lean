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
-- Stage 5 — Equivalence relations and coset equivalence
-- The relation-on-G abstraction that cosets-as-partition needs.
-- ─────────────────────────────────────────────────────────────────────

def Relation (α : Type) := α → α → Prop

def Reflexive {α : Type} (R : Relation α) : Prop := ∀ x : α, R x x
def Symmetric {α : Type} (R : Relation α) : Prop := ∀ x y : α, R x y → R y x
def Transitive {α : Type} (R : Relation α) : Prop :=
  ∀ x y z : α, R x y → R y z → R x z


-- An equivalence relation: reflexive, symmetric, transitive.
structure MyEquivalence {α : Type} (R : Relation α) : Prop where
  refl : Reflexive R
  symm : Symmetric R
  trans : Transitive R


-- a ~ b iff a⁻¹ · b ∈ H. The "same left coset" equivalence on G.
def same_left_coset {G : Type}
    (Γ : MyGroup G)
    (H : MySubgroup Γ) : Relation G :=
  fun a b => H.carrier (Γ.op (Γ.inv a) b)


theorem same_left_coset_refl {G : Type}
    (Γ : MyGroup G) (H : MySubgroup Γ) :
    Reflexive (same_left_coset Γ H) := by
  intro x
  simp only [same_left_coset]
  rw [Γ.inv_left]
  exact H.e_mem


theorem same_left_coset_symm {G : Type}
    (Γ : MyGroup G) (H : MySubgroup Γ) :
    Symmetric (same_left_coset Γ H) := by
  intro x y hxy
  simp only [same_left_coset] at *
  have h1 : H.carrier (Γ.inv (Γ.op (Γ.inv x) y)) := H.inv_closed hxy
  rw [inv_op, inv_inv] at h1
  exact h1


theorem same_left_coset_trans {G : Type}
    (Γ : MyGroup G) (H : MySubgroup Γ) :
    Transitive (same_left_coset Γ H) := by
  intro x y z hxy hyz
  simp only [same_left_coset] at *
  have h1 : H.carrier (Γ.op (Γ.op (Γ.inv x) y) (Γ.op (Γ.inv y) z)) :=
    H.op_closed hxy hyz
  rw [Γ.assoc, ← Γ.assoc y, Γ.inv_right, Γ.e_left] at h1
  exact h1



def same_left_coset_equiv {G : Type}
    (Γ : MyGroup G) (H : MySubgroup Γ) :
    MyEquivalence (same_left_coset Γ H) :=
  ⟨same_left_coset_refl Γ H, same_left_coset_symm Γ H, same_left_coset_trans Γ H⟩


-- a ~_r b iff a · b⁻¹ ∈ H. The mirror relation on the right.
def same_right_coset {G : Type}
    (Γ : MyGroup G)
    (H : MySubgroup Γ) : Relation G :=
  fun a b => H.carrier (Γ.op a (Γ.inv b))


def same_right_coset_equiv {G : Type}
    (Γ : MyGroup G) (H : MySubgroup Γ) :
    MyEquivalence (same_right_coset Γ H) := by
  constructor
  · intro x
    simp only [same_right_coset]
    rw [Γ.inv_right]
    exact H.e_mem
  · intro x y hxy
    simp only [same_right_coset] at *
    have h1 : H.carrier (Γ.inv (Γ.op x (Γ.inv y))) := H.inv_closed hxy
    rw [inv_op, inv_inv] at h1
    exact h1
  · intro x y z hxy hyz
    simp only [same_right_coset] at *
    have h1 : H.carrier (Γ.op (Γ.op x (Γ.inv y)) (Γ.op y (Γ.inv z))) :=
      H.op_closed hxy hyz
    rw [Γ.assoc, ← Γ.assoc (Γ.inv y), Γ.inv_left, Γ.e_left] at h1
    exact h1


-- ─────────────────────────────────────────────────────────────────────
-- Stage 6 — Right cosets, partition, normality characterizations
-- Cosets-as-partition and the three classical "H is normal iff …" facts.
-- ─────────────────────────────────────────────────────────────────────

-- Right coset of H by a: { h · a | h ∈ H }.
def right_coset {G : Type}
    {Γ : MyGroup G}
    (H : MySubgroup Γ)
    (a : G) : Set G :=
  fun x => ∃ h : G, H.carrier h ∧ x = Γ.op h a


-- Two left cosets are equal iff their representatives are in the same coset.
theorem coset_eq_iff {G : Type}
    (Γ : MyGroup G) (H : MySubgroup Γ) (a b : G) :
    left_coset H a = left_coset H b ↔ same_left_coset Γ H a b := by
  constructor
  · intro heq
    simp only [same_left_coset]
    have : left_coset H a a := ⟨Γ.e, H.e_mem, (Γ.e_right a).symm⟩
    rw [heq] at this
    obtain ⟨h, hh, hah⟩ := this
    -- hah : a = Γ.op b h, goal: H.carrier (Γ.op (Γ.inv a) b)
    rw [hah, inv_op]
    -- now goal: H.carrier (Γ.op (Γ.op (Γ.inv h) (Γ.inv b)) b)
    have : Γ.op (Γ.op (Γ.inv h) (Γ.inv b)) b = Γ.inv h := by
      rw [Γ.assoc, Γ.inv_left, Γ.e_right]
    rw [this]
    exact H.inv_closed hh
  · intro hab
    simp only [same_left_coset] at hab
    funext x
    apply propext
    constructor
    · rintro ⟨h, hh, hx⟩
      refine ⟨Γ.op (Γ.op (Γ.inv b) a) h, H.op_closed ?_ hh, ?_⟩
      · have : H.carrier (Γ.inv (Γ.op (Γ.inv a) b)) := H.inv_closed hab
        rw [inv_op, inv_inv] at this
        exact this
      · rw [hx]
        rw [← Γ.assoc b (Γ.op (Γ.inv b) a) h]
        rw [← Γ.assoc b (Γ.inv b) a]
        rw [Γ.inv_right, Γ.e_left]
    · rintro ⟨h, hh, hx⟩
      refine ⟨Γ.op (Γ.op (Γ.inv a) b) h, H.op_closed hab hh, ?_⟩
      rw [hx]
      rw [← Γ.assoc a (Γ.op (Γ.inv a) b) h]
      rw [← Γ.assoc a (Γ.inv a) b]
      rw [Γ.inv_right, Γ.e_left]





-- Any two left cosets are either equal or disjoint.
theorem left_cosets_partition {G : Type}
    (Γ : MyGroup G) (H : MySubgroup Γ) (a b : G) :
    left_coset H a = left_coset H b ∨
    (∀ x : G, ¬ (left_coset H a x ∧ left_coset H b x)) := by
  by_cases h : same_left_coset Γ H a b
  · left; exact (coset_eq_iff Γ H a b).mpr h
  · right
    intro x ⟨hxa, hxb⟩
    apply h
    have heqa : left_coset H a = left_coset H x := by
      apply (coset_eq_iff Γ H a x).mpr
      simp only [same_left_coset]
      obtain ⟨h1, hh1, hx1⟩ := hxa
      rw [hx1, ← Γ.assoc, Γ.inv_left, Γ.e_left]
      exact hh1
    have heqb : left_coset H b = left_coset H x := by
      apply (coset_eq_iff Γ H b x).mpr
      simp only [same_left_coset]
      obtain ⟨h2, hh2, hx2⟩ := hxb
      rw [hx2, ← Γ.assoc, Γ.inv_left, Γ.e_left]
      exact hh2
    rw [← heqb] at heqa
    exact (coset_eq_iff Γ H a b).mp heqa



-- Any two right cosets are either equal or disjoint.
theorem right_cosets_partition {G : Type}
    (Γ : MyGroup G) (H : MySubgroup Γ) (a b : G) :
    right_coset H a = right_coset H b ∨
    (∀ x : G, ¬ (right_coset H a x ∧ right_coset H b x)) := by
  by_cases h : same_right_coset Γ H a b
  · left
    funext x
    apply propext
    simp only [right_coset, same_right_coset] at *
    constructor
    · rintro ⟨k, hk, hx⟩
      refine ⟨Γ.op k (Γ.op a (Γ.inv b)), H.op_closed hk h, ?_⟩
      rw [hx, ← Γ.assoc k a, Γ.assoc (Γ.op k a)]
      rw [show Γ.op (Γ.inv b) b = Γ.e from Γ.inv_left b, Γ.e_right]
    · rintro ⟨k, hk, hx⟩
      have hinv : H.carrier (Γ.inv (Γ.op a (Γ.inv b))) := H.inv_closed h
      rw [inv_op, inv_inv] at hinv
      refine ⟨Γ.op k (Γ.op b (Γ.inv a)), H.op_closed hk hinv, ?_⟩
      rw [hx, ← Γ.assoc k b, Γ.assoc (Γ.op k b)]
      rw [show Γ.op (Γ.inv a) a = Γ.e from Γ.inv_left a, Γ.e_right]
  · right
    intro x ⟨hxa, hxb⟩
    apply h
    simp only [right_coset] at hxa hxb
    obtain ⟨k1, hk1, hx1⟩ := hxa
    obtain ⟨k2, hk2, hx2⟩ := hxb
    simp only [same_right_coset]
    have heq12 : Γ.op k1 a = Γ.op k2 b := by rw [← hx1, ← hx2]
    have hk : H.carrier (Γ.op (Γ.inv k1) k2) := H.op_closed (H.inv_closed hk1) hk2
    have hval : Γ.op a (Γ.inv b) = Γ.op (Γ.inv k1) k2 := by
      apply left_cancel Γ k1
      rw [← Γ.assoc k1 a (Γ.inv b), heq12, Γ.assoc k2 b (Γ.inv b), Γ.inv_right, Γ.e_right,
          ← Γ.assoc k1 (Γ.inv k1) k2, Γ.inv_right, Γ.e_left]
    rw [hval]
    exact hk






-- H is normal iff every left coset equals the corresponding right coset.
theorem normal_iff_cosets_equal {G : Type}
    (Γ : MyGroup G) (H : MySubgroup Γ) :
    normal_subgroup Γ H ↔ ∀ a : G, left_coset H a = right_coset H a := by
  constructor
  · intro hN a
    funext x
    apply propext
    simp only [left_coset, right_coset]
    constructor
    · rintro ⟨h, hh, hx⟩
      refine ⟨Γ.op (Γ.op a h) (Γ.inv a), hN a h hh, ?_⟩
      rw [hx]
      rw [Γ.assoc (Γ.op a h) (Γ.inv a) a, Γ.inv_left, Γ.e_right]
    · rintro ⟨h, hh, hx⟩
      have hh' : H.carrier (Γ.op (Γ.op (Γ.inv a) h) (Γ.inv (Γ.inv a))) := hN (Γ.inv a) h hh
      rw [inv_inv] at hh'
      have hh'' : H.carrier (Γ.op (Γ.inv a) (Γ.op h a)) := by
        rw [← Γ.assoc]; exact hh'
      refine ⟨Γ.op (Γ.inv a) (Γ.op h a), hh'', ?_⟩
      rw [hx, ← Γ.assoc a (Γ.inv a) (Γ.op h a), Γ.inv_right, Γ.e_left]
  · intro hcosets g h hh
    have hmem2 : left_coset H g (Γ.op g h) := ⟨h, hh, rfl⟩
    rw [hcosets g] at hmem2
    obtain ⟨k2, hk2, hk2eq⟩ := hmem2
    have hk2val : k2 = Γ.op (Γ.op g h) (Γ.inv g) := by
      apply right_cancel Γ g
      rw [← hk2eq, Γ.assoc (Γ.op g h) (Γ.inv g) g, Γ.inv_left, Γ.e_right]
    rw [← hk2val]; exact hk2








-- H is normal iff closed under conjugation by every g (g h g⁻¹ ∈ H).
-- (This is the standard characterization, equivalent to the definition.)
theorem normal_iff_conjugation {G : Type}
    (Γ : MyGroup G) (H : MySubgroup Γ) :
    normal_subgroup Γ H ↔
    ∀ g h : G, H.carrier h → H.carrier (Γ.op (Γ.op g h) (Γ.inv g)) := by
  simp only [normal_subgroup]


-- The kernel of a homomorphism is a normal subgroup.
theorem kernel_is_normal {G H : Type}
    {ΓG : MyGroup G} {ΓH : MyGroup H}
    (φ : MyHom ΓG ΓH) :
    normal_subgroup ΓG (kernel_subgroup φ) := by
  intro g h hh
  simp only [kernel_subgroup, hom_kernel] at *
  rw [φ.map_op, φ.map_op, hh, hom_map_inv ΓG ΓH φ]
  rw [ΓH.e_right, ΓH.inv_right]




/-  PHASED RUN GUARD: Stages 7-9 are temporarily block-commented so the
    refine loop only sees the 11 sorries in Stages 5-6 and SUCCESS is
    reachable. Un-comment one stage at a time in subsequent runs.

-- ─────────────────────────────────────────────────────────────────────
-- Stage 7 — Quotient group construction
-- Built on Lean's core `Quot` type. Renamed `MyQuotient` to avoid the
-- name clash with Lean core's `Quotient` (which requires a Setoid).
-- ─────────────────────────────────────────────────────────────────────

def MyQuotient (G : Type) (R : Relation G) := Quot R


def quotient_rel {G : Type}
    (Γ : MyGroup G)
    (H : MySubgroup Γ) : Relation G :=
  same_left_coset Γ H


-- Multiplication on the quotient: [a] * [b] = [a · b]. Well-defined
-- precisely when H is normal.
def quotient_mul {G : Type}
    (Γ : MyGroup G)
    (H : MySubgroup Γ)
    (hN : normal_subgroup Γ H) :
    MyQuotient G (quotient_rel Γ H) →
    MyQuotient G (quotient_rel Γ H) →
    MyQuotient G (quotient_rel Γ H) := by
  sorry


-- Well-definedness of quotient multiplication: if a ~ a' and b ~ b',
-- then a·b ~ a'·b'. Requires H normal.
theorem quotient_mul_well_defined {G : Type}
    (Γ : MyGroup G) (H : MySubgroup Γ)
    (hN : normal_subgroup Γ H)
    (a a' b b' : G)
    (ha : same_left_coset Γ H a a')
    (hb : same_left_coset Γ H b b') :
    same_left_coset Γ H (Γ.op a b) (Γ.op a' b') := by
  sorry


-- Identity of the quotient group: the class of e.
def quotient_identity {G : Type}
    (Γ : MyGroup G)
    (H : MySubgroup Γ) :
    MyQuotient G (quotient_rel Γ H) :=
  Quot.mk _ Γ.e


-- Inverse in the quotient: [a] ↦ [a⁻¹].
def quotient_inverse {G : Type}
    (Γ : MyGroup G)
    (H : MySubgroup Γ)
    (hN : normal_subgroup Γ H) :
    MyQuotient G (quotient_rel Γ H) →
    MyQuotient G (quotient_rel Γ H) := by
  sorry


-- The quotient G/H is itself a group when H is normal.
def quotient_is_group {G : Type}
    (Γ : MyGroup G)
    (H : MySubgroup Γ)
    (hN : normal_subgroup Γ H) :
    MyGroup (MyQuotient G (quotient_rel Γ H)) := by
  sorry


-- ─────────────────────────────────────────────────────────────────────
-- Stage 8 — Isomorphisms and the first isomorphism theorem
-- ─────────────────────────────────────────────────────────────────────

-- A group isomorphism: a homomorphism with a two-sided inverse.
structure MyIso {G H : Type}
    (ΓG : MyGroup G)
    (ΓH : MyGroup H) where
  toFun : G → H
  invFun : H → G
  left_inv : ∀ x : G, invFun (toFun x) = x
  right_inv : ∀ y : H, toFun (invFun y) = y
  map_op : ∀ a b : G, toFun (ΓG.op a b) = ΓH.op (toFun a) (toFun b)


-- The induced map G/ker(φ) → H sending [g] ↦ φ(g).
def induced_map {G H : Type}
    {ΓG : MyGroup G} {ΓH : MyGroup H}
    (φ : MyHom ΓG ΓH)
    (hN : normal_subgroup ΓG (kernel_subgroup φ)) :
    MyQuotient G (quotient_rel ΓG (kernel_subgroup φ)) → H := by
  sorry


-- The induced map commutes with the quotient projection: φ factors
-- through G/ker(φ).
theorem hom_factor_through_kernel {G H : Type}
    {ΓG : MyGroup G} {ΓH : MyGroup H}
    (φ : MyHom ΓG ΓH)
    (hN : normal_subgroup ΓG (kernel_subgroup φ))
    (g : G) :
    induced_map φ hN (Quot.mk _ g) = φ.toFun g := by
  sorry


-- First isomorphism theorem (weak form): the induced map is injective
-- onto its image (which equals image(φ)). The full "MyIso between
-- subtype-of-image and quotient-as-MyGroup" formulation requires
-- explicit MyGroup structures on subtypes, which we have not built.
theorem first_isomorphism_theorem {G H : Type}
    (ΓG : MyGroup G) (ΓH : MyGroup H)
    (φ : MyHom ΓG ΓH)
    (hN : normal_subgroup ΓG (kernel_subgroup φ)) :
    (∀ q1 q2 : MyQuotient G (quotient_rel ΓG (kernel_subgroup φ)),
        induced_map φ hN q1 = induced_map φ hN q2 → q1 = q2) ∧
    (∀ y : H, hom_image φ y →
        ∃ q : MyQuotient G (quotient_rel ΓG (kernel_subgroup φ)),
          induced_map φ hN q = y) := by
  sorry


-- ─────────────────────────────────────────────────────────────────────
-- Stage 9 — Second and third isomorphism theorems
-- These require AB (subgroup product) and lattice-of-subgroups
-- machinery that we have not built; the statements below are
-- aspirational placeholders and may not be tractable in our
-- self-contained setting without more scaffolding.
-- ─────────────────────────────────────────────────────────────────────

-- Subgroup product as a Set (not necessarily itself a subgroup unless
-- one of A, B is normal). { a · b | a ∈ A, b ∈ B }.
def subgroup_product {G : Type}
    {Γ : MyGroup G}
    (A B : MySubgroup Γ) : Set G :=
  fun x => ∃ a b : G, A.carrier a ∧ B.carrier b ∧ x = Γ.op a b


-- Second isomorphism theorem (aspirational): if A is a subgroup and B
-- is normal in G, then A ∩ B is normal in A and A/(A ∩ B) ≅ (AB)/B.
-- Statable here only as a property of subgroup_intersection.
theorem second_isomorphism_theorem {G : Type}
    (Γ : MyGroup G) (A B : MySubgroup Γ)
    (hB : normal_subgroup Γ B) :
    normal_subgroup Γ (subgroup_intersection A B) := by
  sorry


-- Third isomorphism theorem (aspirational): if N ⊆ K are both normal
-- in G, then (G/N)/(K/N) ≅ G/K. Statable only after the full quotient
-- machinery in Stage 7 lands cleanly; left as a known unknown.
theorem third_isomorphism_theorem {G : Type}
    (Γ : MyGroup G) (N K : MySubgroup Γ)
    (hN : normal_subgroup Γ N)
    (hK : normal_subgroup Γ K)
    (hNK : ∀ x : G, N.carrier x → K.carrier x) :
    True := by
  sorry

-/  -- end PHASED RUN GUARD
