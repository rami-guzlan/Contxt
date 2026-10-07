---
name: meal-planner
description: Plan a week of family dinners and the grocery list, safe for a peanut allergy.
triggers:
  - plan meals
  - meal plan
  - what's for dinner this week
  - grocery list
aliases:
  - meals
  - dinner plan
artifacts: []
loads:
  - food/diet
  - food/favorites
  - family/ollie
  - money/budget
  - references/family-recipes.md
quality_gates:
  - no peanuts anywhere
  - within the grocery budget
scope: company
---
# /meal-planner

Plan a week of family dinners and the grocery list.

1. Follow the weekly pattern: soup on Monday, tacos on Tuesday, pizza on Friday, something
   new on Sunday.
2. Mostly vegetarian, fish twice a week, and never peanuts: check every recipe and every
   packaged ingredient for peanuts.
3. Plan easy dinners on Jamie's shift days (Tuesday, Thursday, Saturday).
4. Keep groceries within the $900 monthly budget: about $210 a week.
5. Return the week as a table (day, dinner, prep time) and the grocery list by store aisle.
