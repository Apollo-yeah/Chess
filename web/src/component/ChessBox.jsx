import {
    PIECE_IMAGES,
    PROMOTION_NAMES,
    COL_LABELS,
    ROW_LABELS
} from '../constants/chess_config.js'

import './ChessBox.css'

const ChessBoard = ({ 
    isFlipBoard, 
    selected, 
    legalMovePositions, 
    onClickEvent,
    board,
    lastMove,
}) => {
    const renderedColLabels = isFlipBoard ? [...COL_LABELS].reverse() : COL_LABELS;
    const renderedRowLabels = isFlipBoard ? [...ROW_LABELS].reverse() : ROW_LABELS;
    const renderedBoard = isFlipBoard ? [...board].reverse().map(row => [...row].reverse()) : board;

    const renderedLastMove = isFlipBoard
    ? {
        from: lastMove.from ? { row: 7 - lastMove.from.row, col: 7 - lastMove.from.col } : null,
        to: lastMove.to ? { row: 7 - lastMove.to.row, col: 7 - lastMove.to.col } : null
        }
    : lastMove;

    return (
    <div className="chessboard-container">
        <div className="col-labels">
        {renderedColLabels.map((label) => (
            <div key={label} className="col-label">{label}</div>
        ))}
        </div>
        
        <div className="board-wrapper">
            <div className="row-labels">
                {renderedRowLabels.map((label, idx) => (
                <div key={`row-${idx}-${label}`} className="row-label">{label}</div>
                ))}
            </div>
        
            <div className="chessboard">
                {renderedBoard.map((row, rowIdx) => (
                    <div key={`chess-row-${rowIdx}`} className="chess-row">
                        {row.map((piece, colIdx) => {
                            const actualRow = isFlipBoard ? board.length - 1 - rowIdx : rowIdx;
                            const actualCol = isFlipBoard ? row.length - 1 - colIdx : colIdx;

                            const isSelected = selected != null && selected && selected.row === actualRow && selected.col === actualCol;
                            const isLegalMove = legalMovePositions != null && legalMovePositions.some(pos => pos.row === actualRow && pos.col === actualCol);

                            const isBlackSquare = (rowIdx + colIdx) % 2 === 1;
                            const isLastMoveFrom = renderedLastMove.from?.row === rowIdx && renderedLastMove.from?.col === colIdx;
                            const isLastMoveTo = renderedLastMove.to?.row === rowIdx && renderedLastMove.to?.col === colIdx;
                            const pieceName = PROMOTION_NAMES[piece] || piece;

                            return (
                                <div
                                key={`square-${rowIdx}-${colIdx}`}
                                className={`chess-square 
                                    ${isBlackSquare ? 'black' : 'white'} 
                                    ${isSelected ? 'selected' : ''}
                                    ${isLastMoveFrom ? 'last-move-from' : ''}
                                    ${isLegalMove ? 'legal-move' : ''}
                                    ${isLastMoveTo ? 'last-move-to' : ''}`}
                                onClick={() => onClickEvent(actualRow, actualCol)}
                                >
                                {piece && (
                                    <img
                                    src={PIECE_IMAGES[piece]}
                                    alt={pieceName}
                                    className="piece-image"
                                    title={pieceName}
                                    />
                                )}
                                </div>
                            );
                        })}
                    </div>
                ))}
            </div>
        </div>
    </div>
    );
}

export default ChessBoard;