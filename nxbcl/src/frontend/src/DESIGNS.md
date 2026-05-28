# AGENTS.md

## Project Overview

This project is:

NXBCL Launcher

A blockchain challenge launcher and infrastructure control panel used for spawning, managing, and interacting with blockchain-based CTF challenge environments.

The application is NOT a generic admin dashboard.

The product should feel like:

* infrastructure tooling
* orchestration platform
* blockchain runtime control plane
* DevOps interface
* modern developer tooling

Reference inspirations:

* Vercel Dashboard
* Railway
* Prisma Data Platform
* Tailscale
* Infisical
* Cloudflare Dashboard

---

# Critical Rules

## DO NOT CHANGE APPLICATION LOGIC

You MUST NOT:

* change backend behavior
* modify API structure
* alter business logic
* rename API payloads
* change challenge lifecycle flow
* modify blockchain interaction logic
* change deployment behavior
* modify session handling
* change RPC logic
* alter state management architecture unless explicitly requested

The task is ONLY:

* UI redesign
* component refactor
* layout improvements
* design system implementation
* visual consistency
* spacing improvements
* responsiveness
* component architecture cleanup

This is a frontend modernization task ONLY.

---

# Primary Goal

Transform the current interface into a premium infrastructure-style control panel while preserving all existing functionality.

The redesign should improve:

* readability
* hierarchy
* spacing
* component consistency
* UX clarity
* operational workflow visibility

without changing how the application works.

---

# Visual Direction

The interface should feel:

* technical
* premium
* modern
* infrastructure-focused
* dark-first
* operational
* terminal-native

Avoid:

* generic bootstrap admin
* excessive cyberpunk
* neon overload
* cartoon hacker visuals
* web3 casino aesthetics
* giant rounded cards
* oversized gradients

---

# Design System

## Colors

Background:
#020617

Surface:
#0F172A

Secondary Surface:
#111827

Border:
rgba(148,163,184,0.14)

Text:
#F8FAFC

Muted:
#94A3B8

Primary:
#22D3EE

Blue:
#3B82F6

Violet:
#8B5CF6

Success:
#22C55E

Danger:
#EF4444

Warning:
#F59E0B

---

# Typography

Headings:

* Inter
* Geist

Monospace:

* JetBrains Mono
* Geist Mono

Rules:

* tight heading spacing
* infrastructure-style labels
* uppercase metadata labels
* monospace for technical values
* high readability
* avoid oversized typography

---

# Preferred Stack

Use:

* React
* TailwindCSS
* shadcn/ui
* Framer Motion
* Lucide Icons

Prefer reusable component architecture.

---

# Layout Direction

Preferred structure:

* left sidebar
* top infrastructure header
* main workspace
* responsive dashboard layout

NOT:

* centered landing-page cards
* stacked bootstrap panels

---

# Required UI Sections

## Sidebar

Should contain:

* Sessions
* Challenges
* Wallets
* Logs
* Settings

Sidebar should feel like infrastructure tooling.

---

## Top Header

Contains:

* API status
* RPC node status
* session TTL
* active challenge
* wallet info

Use subtle infra indicators.

---

## Challenge Hero

Main challenge overview section.

Contains:

* challenge title
* category
* status
* chain ID
* session expiration
* action buttons

This should be visually dominant.

---

## Instance Data Grid

Display:

* RPC URL
* Private Key
* Setup Contract
* Wallet Address
* Chain ID

Each item should:

* use monospace text
* support copy button
* use reusable infra card component
* have hover states
* maintain clean spacing

---

## Action Toolbar

Contains actions like:

* Check Solution
* Restart Session
* Extend TTL
* Reset State

Buttons should:

* feel operational
* support loading state
* support disabled state
* use grouped layouts

---

## Terminal Panel

Required section.

Can contain:

* deployment logs
* node logs
* runtime logs
* solver output

Style:

* realistic terminal
* monospace
* compact spacing
* subtle syntax colors

---

# Motion Rules

Use:

* subtle motion
* smooth transitions
* hover lift
* opacity fades
* controlled glow pulse

Avoid:

* chaotic animations
* excessive parallax
* bouncing elements
* distracting movement

---

# Spacing Rules

The current UI suffers from cramped spacing.

Use:

* larger section gaps
* proper padding hierarchy
* consistent card spacing
* aligned grid systems

Avoid:

* tightly packed rows
* inconsistent margins
* random widths

---

# Component Rules

You MUST:

* create reusable components
* avoid giant monolithic files
* separate layout from data logic
* separate visual components from business logic

Preferred folders:

src/components/layout
src/components/ui
src/components/dashboard
src/components/terminal
src/components/challenge

---

# Responsiveness

Desktop-first.

Mobile should:

* stack cards vertically
* collapse sidebar
* preserve readability
* avoid overflowing technical values

---

# Important Constraint

The redesign must preserve:

* all APIs
* all backend integrations
* all blockchain interactions
* all event handlers
* all business workflows
* all challenge orchestration behavior

Only improve presentation and component structure.
