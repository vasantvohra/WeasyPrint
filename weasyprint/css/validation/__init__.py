"""Validate properties, expanders and descriptors."""


from cssselect2 import SelectorError, compile_selector_list
from tinycss2 import parse_blocks_contents, serialize
from tinycss2.ast import FunctionBlock, LiteralToken, WhitespaceToken

from ... import LOGGER
from ..utils import InvalidValues, remove_whitespace
from .expanders import EXPANDERS
from .properties import PREFIX, PROPRIETARY, UNSTABLE, validate_non_shorthand

# Not applicable to the print media
NOT_PRINT_MEDIA = {
    # Aural media
    'azimuth',
    'cue',
    'cue-after',
    'cue-before',
    'elevation',
    'pause',
    'pause-after',
    'pause-before',
    'pitch-range',
    'pitch',
    'play-during',
    'richness',
    'speak-header',
    'speak-numeral',
    'speak-punctuation',
    'speak',
    'speech-rate',
    'stress',
    'voice-family',
    'volume',
    # Animations, transitions, timelines
    'animation',
    'animation-composition',
    'animation-delay',
    'animation-direction',
    'animation-duration',
    'animation-fill-mode',
    'animation-iteration-count',
    'animation-name',
    'animation-play-state',
    'animation-range',
    'animation-range-end',
    'animation-range-start',
    'animation-timeline',
    'animation-timing-function',
    'timeline-scope',
    'transition',
    'transition-delay',
    'transition-duration',
    'transition-property',
    'transition-timing-function',
    'view-timeline',
    'view-timeline-axis',
    'view-timeline-inset',
    'view-timeline-name',
    'view-transition-name',
    # Dynamic and interactive
    'caret',
    'caret-color',
    'caret-shape',
    'cursor',
    'field-sizing',
    'font-display',
    'resize',
    # Browser viewport scrolling
    'overscroll-behavior',
    'overscroll-behavior-block',
    'overscroll-behavior-inline',
    'overscroll-behavior-x',
    'overscroll-behavior-y',
    'scroll-behavior',
    'scroll-margin',
    'scroll-margin-block',
    'scroll-margin-block-end',
    'scroll-margin-block-start',
    'scroll-margin-bottom',
    'scroll-margin-inline',
    'scroll-margin-inline-end',
    'scroll-margin-inline-start',
    'scroll-margin-left',
    'scroll-margin-right',
    'scroll-margin-top',
    'scroll-padding',
    'scroll-padding-block',
    'scroll-padding-block-end',
    'scroll-padding-block-start',
    'scroll-padding-bottom',
    'scroll-padding-inline',
    'scroll-padding-inline-end',
    'scroll-padding-inline-start',
    'scroll-padding-left',
    'scroll-padding-right',
    'scroll-padding-top',
    'scroll-snap-align',
    'scroll-snap-stop',
    'scroll-snap-type',
    'scroll-timeline',
    'scroll-timeline-axis',
    'scroll-timeline-name',
    'scrollbar-color',
    'scrollbar-gutter',
    'scrollbar-width',
}


def preprocess_declarations(base_url, declarations, prelude=None):
    """Expand shorthand properties, filter unsupported properties and values.

    Log a warning for every ignored declaration.

    Return a iterable of ``(name, value, important)`` tuples.

    """
    if prelude is not None:
        try:
            selectors = compile_selector_list(prelude)
        except SelectorError as exc:
            raise SelectorError(f"'{serialize(prelude)}'")

    for declaration in declarations:
        if declaration.type == 'error':
            LOGGER.warning(
                'Error: %s at %d:%d.',
                declaration.message,
                declaration.source_line, declaration.source_column)

        if declaration.type == 'qualified-rule':
            if prelude is None:
                continue
            declaration_prelude = declaration.prelude
            if LiteralToken(1, 1, '&') in declaration.prelude:
                is_token = LiteralToken(1, 1, ':'), FunctionBlock(1, 1, 'is', prelude)
                declaration_prelude = []
                for token in declaration.prelude:
                    if token == LiteralToken(1, 1, '&'):
                        declaration_prelude.extend(is_token)
                    else:
                        declaration_prelude.append(token)
            else:
                is_token = LiteralToken(1, 1, ':'), FunctionBlock(1, 1, 'is', prelude)
                declaration_prelude = [
                    *is_token, WhitespaceToken(1, 1, ' '), *declaration.prelude]
            yield from preprocess_declarations(
                base_url, parse_blocks_contents(declaration.content),
                declaration_prelude)

        if declaration.type != 'declaration':
            continue

        name = declaration.name
        if not name.startswith('--'):
            name = declaration.lower_name

        def validation_error(level, reason):
            getattr(LOGGER, level)(
                'Ignored `%s:%s` at %d:%d, %s.',
                declaration.name, serialize(declaration.value),
                declaration.source_line, declaration.source_column, reason)

        if name in NOT_PRINT_MEDIA:
            validation_error(
                'debug', 'the property does not apply for the print media')
            continue

        if name.startswith(PREFIX):
            unprefixed_name = name[len(PREFIX):]
            if unprefixed_name in PROPRIETARY:
                name = unprefixed_name
            elif unprefixed_name in UNSTABLE:
                LOGGER.warning(
                    'Deprecated `%s:%s` at %d:%d, '
                    'prefixes on unstable attributes are deprecated, '
                    'use %r instead.',
                    declaration.name, serialize(declaration.value),
                    declaration.source_line, declaration.source_column,
                    unprefixed_name)
                name = unprefixed_name
            else:
                LOGGER.warning(
                    'Ignored `%s:%s` at %d:%d, '
                    'prefix on this attribute is not supported, '
                    'use %r instead.',
                    declaration.name, serialize(declaration.value),
                    declaration.source_line, declaration.source_column,
                    unprefixed_name)
                continue

        if name.startswith('-') and not name.startswith('--'):
            validation_error('debug', 'prefixed selectors are ignored')
            continue

        validator = EXPANDERS.get(name, validate_non_shorthand)
        tokens = remove_whitespace(declaration.value)
        try:
            # Having no tokens is allowed by grammar but refused by all
            # properties and expanders.
            if not tokens:
                raise InvalidValues('no value')
            # Use list() to consume generators now and catch any error.
            result = list(validator(tokens, name, base_url))
        except InvalidValues as exc:
            validation_error(
                'warning',
                exc.args[0] if exc.args and exc.args[0] else 'invalid value')
            continue

        important = declaration.important
        for long_name, value in result:
            if prelude is not None:
                declaration = (long_name.replace('-', '_'), value, important)
                yield selectors, declaration
            else:
                yield long_name.replace('-', '_'), value, important
