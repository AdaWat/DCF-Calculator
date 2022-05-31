import yfinance as yf
import pandas as pd

ticker = input("Enter ticker: ").upper()
stock = yf.Ticker(ticker)

pd.set_option('display.max_rows', 500)
pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)


def get_WACC(company):
    # TODO: calculate WACC
    return 0.075


def least_squares_regression(data):
    # predict the next 5 points assuming roughly linear growth
    n = len(data)
    sigma_xy = 0
    for count, i in enumerate(data):
        sigma_xy += (n - count - 1) * i

    sigma_x2 = (n - 1) * n * (2 * n - 1) / 6
    sigma_x = (n - 1) * n / 2
    sigma_y = data.sum()

    slope = (n * sigma_xy - sigma_x * sigma_y) / (n * sigma_x2 - sigma_x ** 2)
    intercept = (sigma_y - slope * sigma_x) / n

    points = []
    for i in range(5):
        points.insert(0, slope * (i + 5) + intercept)

    return points


def dcf(tick, regression=True):
    operatingCashFlow = tick.cashflow.loc["Total Cash From Operating Activities"]
    capitalExpenditure = tick.cashflow.loc["Capital Expenditures"]
    # free cash flow from the past 4 years
    freeCashFlow = operatingCashFlow + capitalExpenditure   # capitalExpenditure is negative

    # revenue going back 4 years
    pastRevenue = tick.financials.loc["Total Revenue"]
    pastNetIncome = tick.financials.loc["Net Income"]
    pastNetIncomeMargins = pastNetIncome / pastRevenue

    if tick.analysis["Revenue Estimate Number Of Analysts"][0] > 0:
        # estimated revenue for this year and next
        projectedRevenue = tick.analysis["Revenue Estimate Avg"].loc[["+1Y", "0Y"]]
        # the growth rate of the estimated revenue from this year and next (used for projecting revenue further into future)
        projectedRevenueGrowthAvg = (tick.analysis["Revenue Estimate Growth"]["0Y"] + tick.analysis["Revenue Estimate Growth"]["+1Y"]) / 2 + 1
        # Add 3 more years to the projectedRevenue list
        projectedRevenue.loc["+2Y"] = projectedRevenue.loc["+1Y"] * projectedRevenueGrowthAvg
        projectedRevenue.loc["+3Y"] = projectedRevenue.loc["+1Y"] * projectedRevenueGrowthAvg**2
        projectedRevenue.loc["+4Y"] = projectedRevenue.loc["+1Y"] * projectedRevenueGrowthAvg**3
        projectedRevenue = projectedRevenue.reindex(["+4Y", "+3Y", "+2Y", "+1Y", "0Y"])
    else:
        # create projected revenue from previous revenue
        projectedRevenue = pd.Series(least_squares_regression(pastRevenue))

    if regression:
        # projecting the net income margins for the next few years
        projectedNetIncomeMargins = least_squares_regression(pastNetIncomeMargins)
    else:
        projectedNetIncomeMargins = pastNetIncomeMargins.mean()

    projectedNetIncome = projectedRevenue * projectedNetIncomeMargins

    # rate of growth of free cash flow
    freeCashFlowRatesStdDev = (freeCashFlow / pastNetIncome).agg("std")
    if freeCashFlowRatesStdDev > 1:     # use median to eliminate outliers if data is wide spread
        freeCashFlowRate = (freeCashFlow / pastNetIncome).median()
    else:
        freeCashFlowRate = (freeCashFlow / pastNetIncome).mean()

    # TODO: check is this is correct (MRNA on Simply Wall Street disagrees)
    projectedFreeCashFlow = projectedNetIncome * freeCashFlowRate

    requiredReturn = get_WACC(tick)
    sharesOutstanding = tick.info["sharesOutstanding"]
    perpetualGrowthRate = 0.025     # also called constant growth rate: rate at which FCF grows forever (could change this)

    # value of cash flow at the end of the last projected period
    terminalValue = projectedFreeCashFlow.iloc[0]*(1+perpetualGrowthRate)/(requiredReturn-perpetualGrowthRate)
    # add terminal value of cash flow to end of projectedFreeCashFlow dataframe
    projectedFreeCashFlow.loc["terminalValue"] = terminalValue
    projectedFreeCashFlow = projectedFreeCashFlow.reindex(["terminalValue", "+4Y", "+3Y", "+2Y", "+1Y", "0Y"])

    # create DataFrame of discount factors going forward a few years
    discountFactors = {"terminalValue": [], "+4Y": [], "+3Y": [], "+2Y": [], "+1Y": [], "0Y": []}
    for count, i in enumerate(discountFactors):
        discountFactors[i] = [(1+requiredReturn)**(len(discountFactors)-count)]
    discountFactors = pd.DataFrame(discountFactors).iloc[0]

    # DataFrame of the present value of the respective future cash flows
    presentValueOfFutureCashFlows = projectedFreeCashFlow / discountFactors
    presentValueOfCompany = presentValueOfFutureCashFlows.sum()

    fairValue = presentValueOfCompany / sharesOutstanding
    # is fairValue is negative (unprofitable), return 0
    return fairValue if fairValue > 0 else 0


fairValueRegression = dcf(stock, True)
fairValue = dcf(stock, False)
currentPrice = stock.info["currentPrice"]
peg = stock.info["pegRatio"]

print("Current value         = ", currentPrice, "\n")
print("Regression fair value = ", round(fairValueRegression, 2), "(undervalued)" if fairValueRegression > currentPrice else "(overvalued)")
print("Fair value            = ", round(fairValue, 2), "(undervalued)" if fairValue > currentPrice else "(overvalued)")
if fairValueRegression and fairValue:
    print("Average               = ", round((fairValueRegression + fairValue) / 2, 2))
print("PEG Ratio             = ", peg, "(undervalued)" if peg < 1 else "(overvalued)")

# TODO: compare fair value with price targets on stock.info, EV/EBITDA (stock.info["enterpriseToEbitda"]).
# TODO: compare P/E to industry and market average (find market w/ stock.info["market"])
# TODO: use stock.info["recommendationKey"]
