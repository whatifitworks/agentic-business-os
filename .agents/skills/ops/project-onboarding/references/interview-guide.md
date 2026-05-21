# Project Onboarding Interview Guide

Use this reference only when the project-onboarding skill needs question ideas. Ask the smallest useful number of questions. Prefer one adaptive follow-up at a time.

## Baseline

- What is the project or business name?
- What country or region does it operate in?
- What does it sell or provide?
- Who are the main customers, users, clients, or stakeholders?
- What should this assistant protect first: revenue, retention, support quality, delivery reliability, owner time, compliance, or something else?
- What is the first useful result this project should produce?

## Business Model

- How does the business make money or define success?
- What are the leading indicators that things are going well?
- What can go wrong if the assistant acts too aggressively?
- Which decisions should always require owner approval?
- Which actions are safe for the assistant to prepare as drafts?

## Tools And Sources

Ask for tools by category:

- communication: email, Slack, Discord, WhatsApp, phone, SMS
- support: help desk, app-store reviews, tickets, forms
- analytics: product analytics, web analytics, subscription analytics, dashboards
- sales or CRM: pipeline, leads, bookings, proposals
- accounting: accounting software, bank exports, invoices, payouts
- product/dev: GitHub, app stores, issue tracker, CI, deployment
- marketing: email campaigns, SEO, ads, social channels, reviews
- planning: calendar, reminders, project management, docs
- operations: suppliers, inventory, scheduling, fulfillment, delivery

For each important tool, capture:

- what it is used for
- who owns access
- whether an MCP server, API, export, email report, browser workflow, or manual description is likely
- what data would be useful
- what actions should never happen without approval

## Routines

- What happens daily, weekly, monthly, and quarterly?
- What do you repeatedly check manually?
- What messages, reports, drafts, or reminders do you create often?
- What work gets delayed because it is annoying rather than difficult?
- What do you review before making important decisions?
- Which recurring tasks have deadlines or legal/accounting risk?

## Automation Candidates

Good first candidates:

- read-only daily/weekly briefs
- support/review triage with draft replies
- metrics summaries from existing exports or APIs
- recurring obligation reminders
- source file intake and memory review
- draft-only marketing or customer follow-up
- repo/project health checks

Avoid as first candidates:

- sending money
- changing legal/accounting records
- publishing content without review
- replying to customers without approval
- connecting accounts during the interview
- workflows that require private credentials in chat

## Business-Type Prompts

### SaaS Or App

- Where are analytics, subscriptions, support, app-store reviews, roadmap tasks, release notes, and repos?
- Which metric matters first: activation, retention, conversion, churn, support load, or revenue?
- What recurring product reviews should happen weekly?

Starter automations: daily metrics brief, support triage, review scan, weekly retention/conversion review, lifecycle campaign review, dev-task intake.

### Local Service

- Where are bookings, customer messages, invoices, reviews, staff schedules, estimates, and follow-ups?
- Which services have seasonal demand?
- What should happen after a completed job or missed appointment?

Starter automations: missed appointment follow-up, review request drafts, open estimate follow-up, local review scan, invoice reminder draft.

### Restaurant Or Cafe

- Which POS, reservations, delivery apps, accounting, supplier ordering, staff scheduling, and review channels are used?
- Are catering or private event requests important?
- Which daily sales or stock checks matter?

Starter automations: daily sales summary, review monitoring, catering inquiry triage, supplier reminder, weekly local marketing plan.

### Agency Or Consulting

- Where do leads, proposals, client projects, invoices, delivery assets, and meeting notes live?
- What signals show a client project is at risk?
- Which follow-ups are repeated?

Starter automations: lead triage, proposal follow-up, weekly client status brief, invoice follow-up, meeting-note intake.

### Ecommerce

- Where are orders, support, inventory, supplier data, ads, email campaigns, reviews, and returns?
- Which margin, stock, or fulfillment signals should be watched?

Starter automations: order/support triage, weekly stock-risk scan, return reason summary, campaign performance review, review response drafts.
