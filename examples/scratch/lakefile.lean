import Lake
open Lake DSL

package "scratch" where
  version := v!"0.1.0"

@[default_target]
lean_lib «Scratch» where
  -- add library configuration options here
