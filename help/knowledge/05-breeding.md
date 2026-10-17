# Breeding — the Pokémon Nursery

The Nursery is Forge's breeding system: deposit two Pokémon, build their
bond, get an Egg, then walk it until it hatches.

## Commands

| Command | What it does |
| --- | --- |
| `/daycare` | Open the Nursery — deposit or withdraw Pokémon |
| `/breed <p1> <p2>` | Quick breed a pair, e.g. `/breed pikachu ditto` |
| `/eggs` | View your Eggs (max **3** at once) |
| `/hatch` | Care for your Eggs / hatch a ready one |
| `/walk` | Walk Eggs to hatch faster |
| `/warm` | Warm your Eggs |
| `/care` | Care for your Eggs |
| `/breedhelp` | The full in-bot Nursery guide |
| `/lineage <name>` | Family tree of a bred Pokémon, e.g. `/lineage eevee` |

All three of Walk, Warm and Care progress an Egg — the guide describes
them as different ways to do the same job, so use whichever you like.

## Compatibility

- Both parents must be the **same species**, **or** one of them must be
  **Ditto** (Ditto pairs with anything).
- **Legendaries and Mythicals cannot breed.**
- **Baby Pokémon cannot be parents.**

## Bond

Bond grows while the two Pokémon spend time together:

- Higher bond → Eggs appear faster.
- Bond also affects hatch speed and the chance of **inherited talents**.

## Eggs and hatching

- An Egg needs **4–9 Journey Points** to hatch (varies per Egg).
- Progress comes from `/walk`, `/warm` and `/care`.
- **Flame Body** or **Magma Armor** on a party member halves the journey.
- The Egg shows stages as it progresses: quiet → moved → something
  inside → a faint cry → cracking → hatching.
- `/camp <name>` puts a Pokémon away to recover and bond for 2 days;
  `/leavecamp <name>` recalls it early (costs are shown in the Nursery).

## What the offspring inherits

- Parents pass **3 IVs** to the child; holding a **Destiny Knot** raises
  that to **5 IVs**.
- An **Everstone** holder passes its **Nature**.
- Inherited moves: parents can teach special moves.
- Inherited talent: a rare bonus that comes from a strong bond.
- Growth potential is graded Normal → Good → Great → Excellent →
  Exceptional based on total IV potential.

## Shiny chances when breeding

- Base: **1 in 1024**
- **Masuda Method** (parents from different generations): **6×**
- **Shiny Charm**: **3×** — and it stacks with Masuda.

## Family history

Every bred Pokémon keeps a lineage record. `/lineage <name>` shows the
family tree, including which parents produced it.
