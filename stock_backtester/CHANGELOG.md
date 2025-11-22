Project Changelog
All notable changes to this project will be documented in this file.

[Unreleased]
Architectural Changes
Standardized on Strategy Instance: Refactored the Optimizer and BacktestEngine to consistently use a pre-configured Strategy instance instead of passing the Strategy class. This simplifies the logic, prevents bugs related to parameter inheritance, and makes the framework's dependency flow cleaner.

Single-Symbol Refactoring: Refactored the YFinanceProvider to handle only a single ticker at a time. This simplifies the data fetching and standardization logic, making the provider more predictable and easier to maintain. All dependent modules were updated to reflect this single-symbol design.

Explicit Dependency Injection in Strategy: Modified the Strategy base class to accept its helper objects (data, portfolio, broker) through the constructor. This improves IDE support, makes dependencies explicit, and enhances testability.

Bug Fixes
Optimizer No-Trade Bug: Resolved a critical bug where the optimizer would fail to apply parameters to the strategy, resulting in no trades being executed during optimization runs.

Final Equity Calculation Accuracy: Fixed a timing bug in the BacktestEngine where the final commission on the last trade was not reflected in the final equity record. The engine now correctly liquidates open positions and updates the final equity record after the event loop finishes.

Portfolio Commission Bug: Corrected a bug in the Portfolio.update_fill method where commissions were not being subtracted on sell trades.

Data Standardization Errors: Made the data standardization process in the YFinanceProvider and example scripts more robust to handle various column formats (tuples, capitalized names) returned by the yfinance library.

Features
Parameter Optimization: Added an Optimizer class to systematically test a grid of strategy parameters and identify the combination with the highest Sharpe Ratio.

Support & Resistance Tool: Added a tools module with a function to identify and plot support and resistance levels from historical price data.

Performance Analyzer: Implemented a PerformanceAnalyzer to calculate and report key metrics like Total Return, CAGR, Sharpe Ratio, Max Drawdown, and detailed trade statistics.