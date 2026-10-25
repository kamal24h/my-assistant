
فهرست Agentهای موردنیاز برای یک Local RAG Multi-Agent در LangGraph (ویژه دستیار ERP و مستندات محصول):

## **لایه ورودی و درک**

# Query Normalizer Agent
– نرمال‌سازی و پاک‌سازی اولیه پرسش (املا، فاصله‌گذاری، یکسان‌سازی اصطلاحات)

# Intent Detection Agent
– کشف نیت کاربر (پرسش اطلاعاتی، درخواست عملیات، راهنمای گام‌به‌گام، شکایت/باگ)

# Language & Domain Detector Agent
– تشخیص زبان و دامنه (ERP / مستندات محصول / عمومی)

# Query Rewriter Agent
– بازنویسی پرسش به کوئری بهینه برای بازیابی

# Query Expansion Agent
– افزودن مترادف‌ها و اصطلاحات فنی مرتبط (مثلاً "فاکتور" → "invoice, bill")

# HyDE Agent
– تولید پاسخ فرضی برای بهبود بازیابی معنایی

## **لایه بازیابی (Retrieval)**

# Embedding Agent
– تولید بردار پرسش با مدل embedding محلی

# Router Agent
– مسیریابی به منبع/ایندکس مناسب (ERP docs / product docs / KB)

# Retriever Agent
– اجرای جستجوی برداری (Dense)

# Sparse Retriever Agent
– جستجوی کلیدواژه‌ای (BM25)

# Hybrid Fusion Agent – ترکیب نتایج Dense و Sparse (RRF)

# Reranker Agent – رتبه‌بندی مجدد نتایج با Cross-Encoder محلی

# Context Compressor Agent – فشرده‌سازی و حذف بخش‌های نامرتبط context

# Relevance Grader Agent – ارزیابی مرتبط بودن اسناد بازیابی‌شده

# Query Retry Agent – تلاش مجدد با کوئری اصلاح‌شده در صورت عدم کفایت نتایج

# **لایه استدلال و تولید**

# Supervisor / Orchestrator Agent – هدایت و هماهنگی سایر ایجنت‌ها

# ERP Specialist Agent – پاسخ تخصصی به سوالات فرآیندهای ERP

# Product Docs Specialist Agent – پاسخ تخصصی به مستندات محصول

# Tool-Calling Agent – فراخوانی ابزارها (جستجو، محاسبه، API داخلی)

# Reasoning Agent – استدلال چندمرحله‌ای روی context

# Answer Generator Agent – تولید پاسخ اولیه

# Citation Agent – افزودن ارجاع به منابع

# Summarizer Agent – خلاصه‌سازی برای پاسخ‌های طولانی

# **لایه اصلاح و کیفیت پاسخ**

# Grammar & Syntax Corrector Agent – اصلاح نحوی و نگارشی پاسخ

# Tone & Style Agent – تنظیم لحن (رسمی/دوستانه) متناسب با کاربر

# Hallucination Checker Agent – بررسی توهم و تطابق با منابع

# Consistency Agent – بررسی سازگاری با پاسخ‌های قبلی

# PII / Security Filter Agent – حذف اطلاعات حساس

# Formatting Agent – قالب‌بندی خروجی (Markdown، جدول، لیست مراحل)

# **لایه حافظه و زمینه**

# Short-Term Memory Agent – مدیریت تاریخچه گفتگو

# Long-Term Memory Agent – ذخیره و بازیابی دانش پایدار کاربر

# User Profile Agent – پروفایل کاربر (نقش، سطح دسترسی، ترجیحات)

# Session Context Agent – حفظ زمینه جلسه جاری

# **لایه ایمنی و کنترل**

# Guardrail Agent – فیلتر ورودی/خروجی نامناسب

# Permission Agent – بررسی سطح دسترسی کاربر در ERP

# Human-in-the-Loop Agent – توقف برای تأیید انسانی در عملیات حساس

# Fallback Agent – مدیریت شرایط خطا و عدم پاسخ

# **لایه پایش و بهبود**

# Feedback Collector Agent – جمع‌آوری بازخورد کاربر

# Logging & Tracing Agent – ثبت رخدادها برای دیباگ

# Evaluation Agent – ارزیابی کیفیت پاسخ‌ها به‌صورت پیوسته

# **لایه ویژه ERP**

# Business Rule Agent – اعمال قوانین کسب‌وکار

# Data Lookup Agent – واکشی داده از دیتابیس ERP

# Action Executor Agent – اجرای عملیات (ایجاد سفارش، به‌روزرسانی رکورد)

