// PGN 历史步骤组件
const PGNHistoryWidget = ({ rounds = [], currentStep = 0, goToStep = () => {} }) => {
    return (
          <div className="moves-list-section">
            <h3 className="section-title">走棋记录</h3>
            <div className="moves-container">
              {rounds.map(({ round, white, black, whiteIndex, blackIndex }) => (
                <div key={`round-${round}`} className="move-round">
                  <span
                    className={`move white ${currentStep === whiteIndex ? 'active' : ''}`}
                    onClick={() => goToStep(whiteIndex)}
                  >
                    {round}. {white?.notation.replace(/^\d+\.\s*/, '')}
                  </span>

                  <span> </span>

                  {black && (
                    <span
                      className={`move black ${currentStep === blackIndex ? 'active' : ''}`}
                      onClick={() => goToStep(blackIndex)}
                    >
                      {black.notation.replace(/^\d+\.\s*/, '')}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
    );
};

export default PGNHistoryWidget;