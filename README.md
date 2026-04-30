# Stock Analysis Dashboard

A personal stock research and portfolio monitoring dashboard built for investors who want deep insight without switching between a dozen tools. Stock Analysis Dashboard pulls live market data, financial statements, and news for every stock on your watchlist, then runs it all through a local AI model to generate investment theses, risk assessments, and event-driven action plans — giving you a clear, up-to-date picture of each position in one place.

## Features

- **Watchlist Management**: Add or remove tickers from your personal watchlist, with all fetched data persisting between sessions

- **Price & Fundamentals**: Tracks current price, volume, market cap, sector, earnings dates, dividends, and upcoming events for each stock

- **Financial Statements**: Pulls quarterly and annual income statements, balance sheets, and cash flow data

- **AI Analysis**: Generates a written investment thesis with bullish, neutral, or bearish sentiment, alongside risk factors, short-selling warnings, and portfolio-level recommendations

- **Event Impact Predictions**: AI-powered forecasts for how upcoming earnings, dividends, and other events may affect price movement

- **News Sentiment**: Fetches recent news per ticker and analyzes its likely price impact with specific trading implications

- **Follow-up Plans**: AI-generated action plans for upcoming events so you know exactly what to watch for and when

- **Daily Gainers**: Surfaces the top 10 movers on US and Canadian markets each day

- **Smart Refresh**: Only re-fetches data that is actually stale — prices every 24 hours, financials when new quarters drop, earnings calendar every 7 days

## Watchlist

- Tracks a customizable list of tickers you care about
- Add or remove stocks at any time
- All fetched data is saved locally so nothing needs to be re-pulled on every visit
- Background fetching keeps the dashboard non-blocking while data updates

## AI Analysis

- Generates a written investment thesis for each stock
- Classifies overall sentiment as bullish, neutral, or bearish
- Identifies key risk factors and flags potential short-selling concerns
- Produces a cross-portfolio recommendation comparing all watchlist stocks

## News & Sentiment

- Pulls recent news articles for each ticker
- Analyzes whether coverage is likely to move the stock up or down
- Notes specific trading implications for each news item
- Supports both 7-day lookback and today-only modes

## Event Tracking

- Monitors upcoming earnings calls, dividend dates, and ex-dividend dates
- Generates follow-up action plans tailored to each event type
- Predicts likely price impact before the event occurs
- Stores plans so they are ready instantly when you need them

## Daily Gainers

- Shows the top 10 price movers on US and Canadian markets
- Lets you spot momentum plays outside your existing watchlist
- Updates each session automatically

## Smart Refresh

- Tracks when each data type was last fetched
- Prices refresh every 24 hours
- Financial statements update only when a new quarter or annual period is available
- Earnings calendars sync every 7 days
- Avoids unnecessary API calls while keeping data current
